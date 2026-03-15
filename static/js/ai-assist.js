/**
 * AI Assist — floating button + modal for LLM-powered data editing.
 *
 * Reads page context from window.__aiContext (set by the AiAssistMixin),
 * sends it with the user's query to /ai-assist/, and displays proposed edits.
 */

function aiAssist() {
  return {
    open: false,
    query: '',
    loading: false,
    summary: '',
    edits: [],
    error: '',
    applied: false,

    get hasContext() {
      return window.__aiContext && Object.keys(window.__aiContext).length > 0;
    },

    async ask() {
      if (!this.query.trim()) return;

      this.loading = true;
      this.summary = '';
      this.edits = [];
      this.error = '';
      this.applied = false;

      try {
        const resp = await fetch('/ai-assist/', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': this._getCsrf(),
          },
          body: JSON.stringify({
            context: window.__aiContext || {},
            query: this.query,
          }),
        });

        if (!resp.ok) {
          this.error = `Server error: ${resp.status}`;
          this.loading = false;
          return;
        }

        const data = await resp.json();
        this.summary = data.summary || '';
        this.edits = (data.edits || []).map(e => ({ ...e, accepted: true }));
        if (data.error) this.error = data.error;
      } catch (err) {
        this.error = `Request failed: ${err.message}`;
      }

      this.loading = false;
    },

    async applyEdits() {
      const accepted = this.edits.filter(e => e.accepted);
      if (!accepted.length) return;

      this.loading = true;
      this.error = '';

      try {
        const resp = await fetch('/ai-assist/apply/', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': this._getCsrf(),
          },
          body: JSON.stringify({ edits: accepted }),
        });

        const data = await resp.json();
        if (data.errors && data.errors.length) {
          this.error = data.errors.join('; ');
        }
        if (data.applied && data.applied.length) {
          this.applied = true;
        }
      } catch (err) {
        this.error = `Apply failed: ${err.message}`;
      }

      this.loading = false;
    },

    reset() {
      this.query = '';
      this.summary = '';
      this.edits = [];
      this.error = '';
      this.applied = false;
    },

    close() {
      this.open = false;
      if (this.applied) {
        window.location.reload();
      }
    },

    _getCsrf() {
      const cookie = document.cookie.split(';').find(c => c.trim().startsWith('csrftoken='));
      return cookie ? cookie.split('=')[1] : '';
    },
  };
}
