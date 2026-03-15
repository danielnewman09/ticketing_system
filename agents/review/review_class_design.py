"""
Deterministic class design review.

Validates that ontology triples represent realizable OO relationships
by checking (subject_kind, predicate, object_kind) against a set of
rules derived from standard design patterns.

This is NOT an LLM agent — it runs purely on the graph structure.
"""

from difflib import SequenceMatcher

from codebase.models import OntologyNode, OntologyTriple
from codebase.models.ontology import TYPE_KINDS, VALUE_KINDS


# ---------------------------------------------------------------------------
# Valid relationship rules
# ---------------------------------------------------------------------------
# Each entry: predicate -> set of (subject_kind, object_kind) pairs that
# are semantically valid.  Anything not listed is a violation.

# Callables: free functions and methods.
_CALLABLE_KINDS = {"function", "method"}

# Kinds that are valid targets for composition (owned by a type).
_COMPOSABLE_KINDS = TYPE_KINDS | {"primitive", "attribute", "constant", "method"}

VALID_RELATIONSHIPS = {
    # Inheritance: type generalizes type
    "generalizes": {
        (s, o) for s in TYPE_KINDS for o in TYPE_KINDS
    },

    # Composition: type composes type/primitive/attribute/constant/method;
    # enum composes enum_value
    "composes": {
        (s, o)
        for s in TYPE_KINDS
        for o in _COMPOSABLE_KINDS
    } | {("enum", "enum_value")},

    # Aggregation: same as composition but weaker ownership
    "aggregates": {
        (s, o)
        for s in TYPE_KINDS
        for o in TYPE_KINDS | {"primitive"}
    },

    # Realization: type realizes interface
    "realizes": {
        (s, "interface")
        for s in TYPE_KINDS
    },

    # Dependency: type/callable depends on type/primitive
    "depends_on": {
        (s, o)
        for s in TYPE_KINDS | _CALLABLE_KINDS
        for o in TYPE_KINDS | {"primitive"}
    },

    # Invocation: callable invokes callable
    "invokes": {
        (s, o) for s in _CALLABLE_KINDS for o in _CALLABLE_KINDS
    },

    # Association: type associates with type/primitive
    "associates": {
        (s, o)
        for s in TYPE_KINDS
        for o in TYPE_KINDS | {"primitive"}
    },
}

# Module can contain anything
for pred in VALID_RELATIONSHIPS:
    VALID_RELATIONSHIPS[pred].add(("module", "module"))


def _reversal_hint(subject_kind, predicate, object_kind):
    """If reversing the direction would be valid, return a hint string."""
    valid_pairs = VALID_RELATIONSHIPS.get(predicate, set())
    if (object_kind, subject_kind) in valid_pairs:
        return (
            f" Note: {object_kind} --{predicate}--> {subject_kind} IS valid "
            f"— consider whether the direction should be reversed."
        )
    return ""


def _suggest_fix(subject_kind, predicate, object_kind):
    """Suggest what the triple should be instead."""
    reversal = _reversal_hint(subject_kind, predicate, object_kind)

    # Attribute as subject — attributes must never be the subject of a triple
    if subject_kind == "attribute":
        return (
            f"An attribute cannot be the subject of a triple. "
            f"Attributes may only appear as the object of a 'composes' "
            f"relationship from their owning class. Either change the "
            f"node's kind to 'class' if it has its own behavior, or "
            f"remove this triple."
        )

    # Class invokes class -> should be depends_on
    if predicate == "invokes" and subject_kind in TYPE_KINDS and object_kind in TYPE_KINDS:
        return (
            f"Classes do not invoke classes — methods invoke methods. "
            f"Change to 'depends_on', or introduce function nodes for the "
            f"specific methods involved."
        )

    # Class invokes function or function invokes class
    if predicate == "invokes":
        if subject_kind in TYPE_KINDS:
            return (
                f"A {subject_kind} cannot invoke directly. Introduce a "
                f"function node as the caller.{reversal}"
            )
        if object_kind in TYPE_KINDS:
            return (
                f"A {subject_kind} cannot invoke a {object_kind}. The "
                f"target should be a function node.{reversal}"
            )

    # Realizes non-interface
    if predicate == "realizes" and object_kind != "interface":
        return (
            f"'realizes' should target an interface, not a {object_kind}. "
            f"Change the target's kind to 'interface' or use 'generalizes'.{reversal}"
        )

    # Generalizes with non-type kinds
    if predicate == "generalizes":
        if subject_kind not in TYPE_KINDS:
            return (
                f"A {subject_kind} cannot generalize. "
                f"Change its kind to a type.{reversal}"
            )
        if object_kind not in TYPE_KINDS:
            return (
                f"Cannot generalize a {object_kind}. "
                f"Change its kind to a type.{reversal}"
            )

    return (
        f"'{predicate}' is not valid between {subject_kind} and "
        f"{object_kind}. Review the relationship and node kinds.{reversal}"
    )


class ClassDesignViolation:
    """A single invalid triple found during review."""

    __slots__ = (
        "triple_id", "subject_qualified_name", "subject_kind",
        "predicate", "object_qualified_name", "object_kind",
        "suggestion",
    )

    def __init__(self, triple, suggestion):
        self.triple_id = triple.id
        self.subject_qualified_name = triple.subject.qualified_name
        self.subject_kind = triple.subject.kind
        self.predicate = triple.predicate.name
        self.object_qualified_name = triple.object.qualified_name
        self.object_kind = triple.object.kind
        self.suggestion = suggestion

    def __str__(self):
        return (
            f"{self.subject_qualified_name} ({self.subject_kind}) "
            f"--{self.predicate}--> "
            f"{self.object_qualified_name} ({self.object_kind}): "
            f"{self.suggestion}"
        )


class NameCollisionViolation:
    """Multiple nodes share the same short name across namespaces."""

    __slots__ = ("name", "qualified_names", "suggestion")

    def __init__(self, name, qualified_names):
        self.name = name
        self.qualified_names = qualified_names

        # Identify unnamespaced nodes (name == qualified_name)
        unnamespaced = [qn for qn in qualified_names if qn == name]
        namespaced = [qn for qn in qualified_names if qn != name]

        parts = []
        if unnamespaced:
            parts.append(
                f"'{name}' exists without a namespace — it should be "
                f"merged into one of the namespaced variants or given a "
                f"distinct name."
            )
        if len(namespaced) >= 2:
            parts.append(
                f"Nodes {', '.join(namespaced)} share the name '{name}'. "
                f"Give each a more descriptive class name rather than "
                f"relying on namespaces to disambiguate "
                f"(e.g., 'CalculatorWindow' vs 'CalculatorEngine')."
            )
        self.suggestion = " ".join(parts)

    def __str__(self):
        return (
            f"Name collision: '{self.name}' used by "
            f"{', '.join(self.qualified_names)}: {self.suggestion}"
        )


class EnumHierarchyViolation:
    """An enum_value node that is not properly nested under its parent enum."""

    __slots__ = ("enum_value_qualified_name", "expected_parent", "suggestion")

    def __init__(self, enum_value_qname, expected_parent_qname=None):
        self.enum_value_qualified_name = enum_value_qname
        self.expected_parent = expected_parent_qname

        if expected_parent_qname:
            self.suggestion = (
                f"enum_value '{enum_value_qname}' should be nested under "
                f"its parent enum '{expected_parent_qname}' as "
                f"'{expected_parent_qname}::{enum_value_qname.rsplit('::', 1)[-1]}'. "
                f"Move it under the enum or remove it if it duplicates an "
                f"existing correctly-nested enum_value."
            )
        else:
            self.suggestion = (
                f"enum_value '{enum_value_qname}' is not nested under any "
                f"enum node. It should be placed under its parent enum "
                f"(e.g., 'MyEnum::{enum_value_qname.rsplit('::', 1)[-1]}') "
                f"or removed if it duplicates an existing correctly-nested "
                f"enum_value."
            )

    def __str__(self):
        return (
            f"Enum hierarchy violation: {self.enum_value_qualified_name} — "
            f"{self.suggestion}"
        )


def _check_enum_hierarchy():
    """Find enum_value nodes not properly nested under an enum.

    An enum_value's qualified_name should start with its parent enum's
    qualified_name followed by '::'.  Any enum_value that doesn't follow
    this pattern is a violation.
    """
    enum_nodes = {
        n.qualified_name
        for n in OntologyNode.objects.filter(kind="enum")
    }
    enum_values = OntologyNode.objects.filter(kind="enum_value")

    violations = []
    for ev in enum_values:
        # Check if this enum_value is nested under any known enum
        parent_qname = ev.qualified_name.rsplit("::", 1)[0] if "::" in ev.qualified_name else ""
        if parent_qname in enum_nodes:
            continue  # correctly nested

        # Try to find which enum it should belong to (by looking at
        # composes triples or by matching name patterns)
        possible_parent = None
        for enum_qname in enum_nodes:
            # Check if there's a composes triple linking them
            if OntologyTriple.objects.filter(
                subject__qualified_name=enum_qname,
                predicate__name="composes",
                object=ev,
            ).exists():
                possible_parent = enum_qname
                break

        violations.append(EnumHierarchyViolation(
            ev.qualified_name, possible_parent,
        ))

    return violations


class AttributeSubjectViolation:
    """An attribute node that appears as the subject of a triple."""

    __slots__ = ("attribute_qualified_name", "triple_str", "suggestion")

    def __init__(self, attribute_qname, triple_str):
        self.attribute_qualified_name = attribute_qname
        self.triple_str = triple_str
        self.suggestion = (
            f"Attribute '{attribute_qname}' is the subject of a triple "
            f"({triple_str}). Attributes must only appear as the object of "
            f"a 'composes' relationship. Either change its kind to 'class' "
            f"if it has its own behavior, or remove this triple."
        )

    def __str__(self):
        return (
            f"Attribute subject violation: {self.attribute_qualified_name} — "
            f"{self.suggestion}"
        )


def _check_attribute_usage():
    """Find attribute nodes misused as triple subjects.

    Attributes should only appear as the object of a 'composes' triple,
    never as the subject of any triple.
    """
    attribute_nodes = OntologyNode.objects.filter(kind="attribute")
    if not attribute_nodes.exists():
        return []

    violations = []
    for attr in attribute_nodes:
        subject_triples = OntologyTriple.objects.filter(
            subject=attr,
        ).select_related("subject", "object", "predicate")
        for t in subject_triples:
            triple_str = (
                f"{t.subject.qualified_name} --{t.predicate.name}--> "
                f"{t.object.qualified_name}"
            )
            violations.append(AttributeSubjectViolation(
                attr.qualified_name, triple_str,
            ))

    return violations


def _check_name_collisions():
    """Find nodes that share the same short name across different namespaces."""
    from collections import defaultdict

    # Only check type-level nodes — functions/variables are expected to repeat
    nodes = OntologyNode.objects.filter(kind__in=TYPE_KINDS)
    by_name = defaultdict(list)
    for node in nodes:
        by_name[node.name].append(node.qualified_name)

    violations = []
    for name, qnames in by_name.items():
        if len(qnames) > 1:
            violations.append(NameCollisionViolation(name, sorted(qnames)))
    return violations


def review_class_design():
    """Check ontology for invalid OO relationships and naming issues.

    Returns a list of ClassDesignViolation and NameCollisionViolation objects.
    """
    violations = []

    # --- Triple relationship checks ---
    triples = OntologyTriple.objects.select_related(
        "subject", "object", "predicate",
    ).all()

    for triple in triples:
        pred_name = triple.predicate.name
        subj_kind = triple.subject.kind
        obj_kind = triple.object.kind

        valid_pairs = VALID_RELATIONSHIPS.get(pred_name)
        if valid_pairs is None:
            # Unknown predicate — skip (could be user-defined)
            continue

        if (subj_kind, obj_kind) not in valid_pairs:
            # A type invoking its own member function is valid
            if (
                pred_name == "invokes"
                and subj_kind in TYPE_KINDS
                and obj_kind == "function"
                and triple.object.qualified_name.startswith(
                    triple.subject.qualified_name + "::"
                )
            ):
                continue

            suggestion = _suggest_fix(subj_kind, pred_name, obj_kind)
            violations.append(ClassDesignViolation(triple, suggestion))

    # --- Enum hierarchy checks ---
    violations.extend(_check_enum_hierarchy())

    # --- Attribute usage checks ---
    violations.extend(_check_attribute_usage())

    # --- Name collision checks ---
    violations.extend(_check_name_collisions())

    return violations


def violations_to_challenges(violations):
    """Convert violation objects to DesignChallenge objects.

    This allows violations to flow into the existing challenge/remediate
    pipeline.
    """
    from agents.review.challenge_design import DesignChallenge

    challenges = []
    for v in violations:
        if isinstance(v, ClassDesignViolation):
            challenges.append(DesignChallenge(
                category="class_design",
                severity="major",
                description=(
                    f"{v.subject_qualified_name} ({v.subject_kind}) "
                    f"--{v.predicate}--> "
                    f"{v.object_qualified_name} ({v.object_kind}) "
                    f"is not a valid OO relationship."
                ),
                affected_node_qualified_names=[
                    v.subject_qualified_name,
                    v.object_qualified_name,
                ],
                remedy_type="restructure_ontology",
                suggested_remedy=v.suggestion,
            ))
        elif isinstance(v, EnumHierarchyViolation):
            affected = [v.enum_value_qualified_name]
            if v.expected_parent:
                affected.append(v.expected_parent)
            challenges.append(DesignChallenge(
                category="class_design",
                severity="critical",
                description=(
                    f"enum_value '{v.enum_value_qualified_name}' is not "
                    f"nested under its parent enum. Enum values must be "
                    f"scoped under their defining enum type."
                ),
                affected_node_qualified_names=affected,
                remedy_type="restructure_ontology",
                suggested_remedy=v.suggestion,
            ))
        elif isinstance(v, AttributeSubjectViolation):
            challenges.append(DesignChallenge(
                category="class_design",
                severity="major",
                description=(
                    f"Attribute '{v.attribute_qualified_name}' is used as "
                    f"the subject of a triple. Attributes must only appear "
                    f"as the object of a 'composes' relationship."
                ),
                affected_node_qualified_names=[v.attribute_qualified_name],
                remedy_type="restructure_ontology",
                suggested_remedy=v.suggestion,
            ))
        elif isinstance(v, NameCollisionViolation):
            challenges.append(DesignChallenge(
                category="class_design",
                severity="major",
                description=(
                    f"Name collision: '{v.name}' is used by multiple nodes: "
                    f"{', '.join(v.qualified_names)}. Nodes should have "
                    f"distinct names rather than relying on namespaces to "
                    f"disambiguate."
                ),
                affected_node_qualified_names=list(v.qualified_names),
                remedy_type="restructure_ontology",
                suggested_remedy=v.suggestion,
            ))
    return challenges


# ---------------------------------------------------------------------------
# Remediation plan sanity check
# ---------------------------------------------------------------------------

_SIMILARITY_THRESHOLD = 0.75


def _name_similarity(a, b):
    """Case-insensitive similarity ratio between two node names."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _build_conflict_context(proposed, existing_qname, existing_node):
    """Build the context dict for one conflict to send to the review agent."""
    from requirements.models import HighLevelRequirement, LowLevelRequirement

    # Existing triples involving this node
    existing_triples = []
    for t in OntologyTriple.objects.filter(
        subject__qualified_name=existing_qname,
    ).select_related("subject", "object", "predicate"):
        existing_triples.append(
            f"{t.subject.qualified_name} --{t.predicate.name}--> {t.object.qualified_name}"
        )
    for t in OntologyTriple.objects.filter(
        object__qualified_name=existing_qname,
    ).select_related("subject", "object", "predicate"):
        existing_triples.append(
            f"{t.subject.qualified_name} --{t.predicate.name}--> {t.object.qualified_name}"
        )

    # HLR/LLR context: requirements linked to triples involving this node
    triple_ids = OntologyTriple.objects.filter(
        subject__qualified_name=existing_qname,
    ).union(
        OntologyTriple.objects.filter(object__qualified_name=existing_qname)
    ).values_list("id", flat=True)

    hlr_context = [
        f"HLR {h.pk}: {h.description}"
        for h in HighLevelRequirement.objects.filter(
            triples__id__in=triple_ids,
        ).distinct()
    ]
    llr_context = [
        f"LLR {l.pk} (HLR {l.high_level_requirement_id}): {l.description}"
        for l in LowLevelRequirement.objects.filter(
            triples__id__in=triple_ids,
        ).distinct()
    ]

    return {
        "proposed_qualified_name": proposed.qualified_name,
        "proposed_kind": proposed.kind,
        "proposed_description": proposed.description,
        "existing_qualified_name": existing_qname,
        "existing_kind": existing_node.kind if existing_node else "unknown",
        "existing_description": (
            existing_node.description if existing_node else ""
        ),
        "existing_triples": existing_triples,
        "proposed_triples": [],  # filled in by caller
        "hlr_context": hlr_context,
        "llr_context": llr_context,
    }


def _is_nested_enum_value(existing_node):
    """Return True if the existing node is an enum_value properly nested under an enum."""
    if existing_node.kind != "enum_value":
        return False
    if "::" not in existing_node.qualified_name:
        return False
    parent_qname = existing_node.qualified_name.rsplit("::", 1)[0]
    return OntologyNode.objects.filter(
        qualified_name=parent_qname, kind="enum",
    ).exists()


def sanitize_new_nodes(plan, prompt_log_file=""):
    """Check proposed new_nodes against existing nodes for near-duplicates.

    When a proposed node's name closely matches an existing node, the
    conflict is sent to the review_node_conflict agent to decide whether
    the proposed name (better OO hierarchy) or the existing name should
    win. The plan is then mutated accordingly:

    - keep_proposed: the existing node is renamed to the proposed
      qualified_name, the proposed node is dropped from new_nodes (it's
      already in the DB under the new name), and triples are left as-is.
    - keep_existing: the proposed node is dropped and new_triples are
      rewritten to reference the existing node.
    - keep_both: no action — both nodes are kept.

    Certain conflicts are resolved deterministically without consulting
    the review agent:
    - An existing enum_value properly nested under its parent enum is
      never replaced by a proposed node of a different kind.

    Returns a list of log messages describing what happened.
    """
    from agents.review.review_node_conflict import review_conflicts

    if not plan.new_nodes:
        return []

    existing_nodes = {
        (n.name, n.qualified_name): n
        for n in OntologyNode.objects.all()
    }

    # Detect conflicts
    conflicts = []  # (proposed, existing_qname, existing_node)
    no_conflict = []

    for proposed in plan.new_nodes:
        best_match = None
        best_score = 0
        best_node = None

        for (existing_name, existing_qname), existing_node in existing_nodes.items():
            if proposed.qualified_name == existing_qname:
                continue  # same node, not a conflict

            # Exact name match in different namespace
            if proposed.name == existing_name:
                best_match = existing_qname
                best_score = 1.0
                best_node = existing_node
                break

            # Fuzzy name similarity
            score = _name_similarity(proposed.name, existing_name)
            if score >= _SIMILARITY_THRESHOLD and score > best_score:
                best_match = existing_qname
                best_score = score
                best_node = existing_node

        if best_match:
            conflicts.append((proposed, best_match, best_node))
        else:
            no_conflict.append(proposed)

    if not conflicts:
        return []

    # Separate conflicts into deterministic (auto-resolved) and agent-reviewed
    messages = []
    keep = list(no_conflict)
    agent_conflicts = []

    for proposed, existing_qname, existing_node in conflicts:
        # Guard: never rename a properly-nested enum_value to a different kind
        if (
            existing_node
            and existing_node.kind == "enum_value"
            and proposed.kind != "enum_value"
            and _is_nested_enum_value(existing_node)
        ):
            # The proposed node is a different kind (e.g., class) that
            # happens to share a name with an enum_value — keep both
            keep.append(proposed)
            messages.append(
                f"Kept proposed '{proposed.qualified_name}' ({proposed.kind}) "
                f"alongside existing enum_value '{existing_qname}' — "
                f"enum values nested under their parent enum are protected."
            )
            continue

        # Guard: never replace an enum with a non-enum of the same name
        if (
            existing_node
            and existing_node.kind == "enum"
            and proposed.kind != "enum"
        ):
            # Drop the proposed node, rewrite triples to existing
            for triple in plan.new_triples:
                if triple.subject_qualified_name == proposed.qualified_name:
                    triple.subject_qualified_name = existing_qname
                if triple.object_qualified_name == proposed.qualified_name:
                    triple.object_qualified_name = existing_qname
            messages.append(
                f"Dropped proposed '{proposed.qualified_name}' ({proposed.kind}) "
                f"— existing enum '{existing_qname}' takes precedence. "
                f"Triples rewritten."
            )
            continue

        agent_conflicts.append((proposed, existing_qname, existing_node))

    # Send remaining conflicts to the review agent
    if agent_conflicts:
        conflict_contexts = []
        for proposed, existing_qname, existing_node in agent_conflicts:
            ctx = _build_conflict_context(proposed, existing_qname, existing_node)

            # Add proposed triples that reference this node
            for t in plan.new_triples:
                if (t.subject_qualified_name == proposed.qualified_name
                        or t.object_qualified_name == proposed.qualified_name):
                    ctx["proposed_triples"].append(
                        f"{t.subject_qualified_name} --{t.predicate}--> "
                        f"{t.object_qualified_name}"
                    )

            conflict_contexts.append(ctx)

        review_result = review_conflicts(
            conflict_contexts, prompt_log_file=prompt_log_file,
        )

        # Build lookup from review results
        resolution_map = {
            r.proposed_qualified_name: r for r in review_result.resolutions
        }

        for proposed, existing_qname, existing_node in agent_conflicts:
            resolution = resolution_map.get(proposed.qualified_name)

            if not resolution:
                keep.append(proposed)
                messages.append(
                    f"No resolution returned for '{proposed.qualified_name}' vs "
                    f"'{existing_qname}' — keeping proposed node."
                )
                continue

            if resolution.action == "keep_proposed":
                OntologyNode.objects.filter(
                    qualified_name=existing_qname,
                ).update(qualified_name=proposed.qualified_name)

                for t in plan.remove_triples:
                    if t.subject_qualified_name == existing_qname:
                        t.subject_qualified_name = proposed.qualified_name
                    if t.object_qualified_name == existing_qname:
                        t.object_qualified_name = proposed.qualified_name

                messages.append(
                    f"Renamed existing node '{existing_qname}' -> "
                    f"'{proposed.qualified_name}' (better OO hierarchy). "
                    f"Rationale: {resolution.rationale}"
                )

            elif resolution.action == "keep_existing":
                for triple in plan.new_triples:
                    if triple.subject_qualified_name == proposed.qualified_name:
                        triple.subject_qualified_name = existing_qname
                    if triple.object_qualified_name == proposed.qualified_name:
                        triple.object_qualified_name = existing_qname

                messages.append(
                    f"Dropped proposed node '{proposed.qualified_name}' in favor "
                    f"of existing '{existing_qname}'. Triples rewritten. "
                    f"Rationale: {resolution.rationale}"
                )

            elif resolution.action == "keep_both":
                keep.append(proposed)
                messages.append(
                    f"Kept both '{proposed.qualified_name}' and "
                    f"'{existing_qname}' (distinct entities). "
                    f"Rationale: {resolution.rationale}"
                )

    plan.new_nodes = keep

    return messages
