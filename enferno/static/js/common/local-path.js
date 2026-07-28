/**
 * Opening data folders held outside Bayanat.
 *
 * Browsers refuse to navigate from an http:// page to file:// or a UNC path,
 * so a local path is handed to the bayanat-open: protocol handler instead
 * (see tools/windows-open-handler). If that helper is not installed the
 * navigation is silently ignored, so the path is always copied as well and the
 * message says so -- the operator is never left with nothing.
 *
 * Shared by Field Data and Bulletins; keep the behaviour in one place.
 */
const localPathMixin = {
  methods: {
    isWebLink(link) {
      return /^https?:\/\//i.test((link || '').trim());
    },

    // D:\... , \\server\share\... or another absolute Windows path.
    isLocalPath(link) {
      const v = (link || '').trim();
      return /^[a-zA-Z]:[\\/]/.test(v) || /^\\\\/.test(v);
    },

    openLink(link) {
      if (!link) return;
      const value = link.trim();
      const t = window.translations || {};

      if (this.isWebLink(value)) {
        window.open(value, '_blank', 'noopener');
        return;
      }

      if (this.isLocalPath(value)) {
        window.location.href = 'bayanat-open:' + encodeURIComponent(value);
        this.copyLink(
          value,
          t.openingInExplorer_ ||
            'Opening in Explorer. If nothing happens the helper is not installed - the path has been copied instead.'
        );
        return;
      }

      this.copyLink(value, t.pathCopied_ || 'Path copied. Paste it into your file explorer.');
    },

    copyLink(link, message) {
      if (!link) return;
      const t = window.translations || {};
      const note = message || t.linkCopied_ || 'Link copied';
      navigator.clipboard
        .writeText(link)
        .then(() => this.showSnack(note))
        .catch(() => this.showSnack(t.couldNotCopyLink_ || 'Could not copy link'));
    },
  },
};
