/**
 * "Request original file" — the gated replacement for a direct download link.
 *
 * Viewing the media is unaffected; this only covers taking a copy off the
 * system. The button walks the user through the three states that flow can be
 * in: nothing requested yet, waiting on an admin, or approved and waiting for
 * the code the admin issued.
 */
const DownloadRequestButton = Vue.defineComponent({
  props: {
    media: { type: Object, required: true },
    // Set false to fall back to a plain download (approval turned off server-side).
    gated: { type: Boolean, default: true },
    directUrl: { type: String, default: '' },
  },

  data() {
    return {
      translations: window.translations || {},
      askOpen: false,
      codeOpen: false,
      reason: '',
      loading: false,
      request: null,
    };
  },

  computed: {
    filename() {
      return this.media?.filename || this.media?.media_file || 'download';
    },
    // Only an approval that is still live and still has attempts left is worth
    // offering a code box for.
    approved() {
      return this.request && this.request.status === 'Approved' && this.request.downloadable;
    },
    pending() {
      return this.request && this.request.status === 'Pending';
    },
    label() {
      if (this.approved) return this.translations.enterCode_ || 'Enter code';
      if (this.pending) return this.translations.awaitingApproval_ || 'Awaiting approval';
      return this.translations.requestFile_ || 'Request file';
    },
    icon() {
      if (this.approved) return 'mdi-shield-key-outline';
      if (this.pending) return 'mdi-clock-outline';
      return 'mdi-download-lock';
    },
  },

  mounted() {
    if (this.gated) this.loadExisting();
  },

  methods: {
    // A request may already be open from an earlier session, so the button
    // has to reflect server state rather than assume a fresh start.
    loadExisting() {
      axios
        .post('/admin/api/download-requests/list', { per_page: 50 })
        .then((response) => {
          const items = response.data?.items || [];
          this.request = items.find(
            (r) => r.media_id === this.media.id
              && ['Pending', 'Approved'].includes(r.status)
              && !r.expired,
          ) || null;
        })
        .catch(() => { /* button just falls back to "Request file" */ });
    },

    click() {
      if (!this.gated) {
        this.plainDownload();
        return;
      }
      if (this.approved) {
        this.codeOpen = true;
      } else if (this.pending) {
        this.$root.showSnack?.(
          this.translations.awaitingApprovalHint_
          || 'An admin has not approved this download yet.',
        );
      } else {
        this.reason = '';
        this.askOpen = true;
      }
    },

    plainDownload() {
      const link = document.createElement('a');
      link.href = this.directUrl;
      link.download = this.filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    },

    submitRequest() {
      if (!this.reason.trim() || this.loading) return;
      this.loading = true;
      axios
        .post('/admin/api/download-requests/', {
          media_id: this.media.id,
          reason: this.reason.trim(),
        }, { suppressGlobalErrorHandler: true })
        .then((response) => {
          this.request = response.data?.item || null;
          this.askOpen = false;
          this.$root.showSnack?.(response.data?.message || 'Request sent.');
        })
        .catch((err) => {
          this.$root.showSnack?.(err?.response?.data?.message || 'Could not send the request');
        })
        .finally(() => { this.loading = false; });
    },

    onDownloaded() {
      // Spent: the approval is one-use, so the button goes back to its start.
      this.request = null;
      this.$root.showSnack?.(this.translations.downloadComplete_ || 'Download complete');
    },
  },

  template: `
    <span>
      <v-tooltip location="top" :text="label">
        <template #activator="{ props }">
          <v-btn v-bind="props" variant="text" size="small"
                 :icon="icon"
                 :color="approved ? 'success' : (pending ? 'warning' : undefined)"
                 @click.stop="click"></v-btn>
        </template>
      </v-tooltip>

      <!-- Ask for a reason: an approver needs something to decide on. -->
      <v-dialog v-model="askOpen" max-width="480" persistent>
        <v-card :loading="loading">
          <v-card-title>{{ translations.requestFile_ || 'Request file' }}</v-card-title>
          <v-card-text>
            <p class="text-body-2 mb-2">{{ filename }}</p>
            <v-alert type="info" variant="tonal" density="compact" class="mb-4">
              {{ translations.downloadRequestHint_ ||
                 'An admin must approve this. They will be given a one-time code to pass to you.' }}
            </v-alert>
            <v-textarea
              v-model="reason"
              rows="3"
              variant="outlined"
              :disabled="loading"
              :label="translations.reasonForDownload_ || 'Why do you need this file?'"
            ></v-textarea>
          </v-card-text>
          <v-card-actions>
            <v-spacer></v-spacer>
            <v-btn variant="text" :disabled="loading" @click="askOpen = false">
              {{ translations.cancel_ || 'Cancel' }}
            </v-btn>
            <v-btn color="primary" variant="flat" :loading="loading"
                   :disabled="!reason.trim()" @click="submitRequest">
              {{ translations.sendRequest_ || 'Send request' }}
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>

      <download-code-dialog
        v-if="request"
        v-model="codeOpen"
        :url="'/admin/api/download-requests/' + request.id + '/download'"
        :filename="filename"
        @downloaded="onDownloaded"
      ></download-code-dialog>
    </span>
  `,
});
