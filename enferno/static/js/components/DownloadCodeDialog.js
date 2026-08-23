/**
 * Collects the one-time verification code and exchanges it for the file.
 *
 * The code never travels through this app: an admin was shown it on approval
 * and passed it to the requester directly. All this does is take it back and
 * post it, because the file is released in the response to that post rather
 * than from any URL that could be bookmarked or shared.
 *
 * Used for both media download requests and export archives -- the two differ
 * only in the endpoint and payload, which the caller supplies.
 */
const DownloadCodeDialog = Vue.defineComponent({
  props: {
    modelValue: { type: Boolean, default: false },
    // Endpoint that trades a code for the file.
    url: { type: String, required: true },
    // Extra body fields (e.g. exportId). The code is added automatically.
    payload: { type: Object, default: () => ({}) },
    filename: { type: String, default: 'download' },
    title: { type: String, default: '' },
  },
  emits: ['update:modelValue', 'downloaded'],

  data() {
    return {
      translations: window.translations || {},
      code: '',
      loading: false,
      error: '',
    };
  },

  computed: {
    open: {
      get() { return this.modelValue; },
      set(v) { this.$emit('update:modelValue', v); },
    },
  },

  watch: {
    modelValue(isOpen) {
      if (isOpen) {
        this.code = '';
        this.error = '';
      }
    },
  },

  methods: {
    close() {
      this.open = false;
    },

    submit() {
      if (!this.code.trim() || this.loading) return;
      this.loading = true;
      this.error = '';

      // responseType blob: a success returns the file bytes, so it must not be
      // parsed as JSON. Errors come back as JSON in a blob and are unpacked below.
      axios
        .post(this.url, { ...this.payload, code: this.code.trim() }, {
          responseType: 'blob',
          suppressGlobalErrorHandler: true,
        })
        .then((response) => {
          const type = response.data?.type || '';
          if (type.includes('application/json')) {
            // S3 deployments answer with a signed URL rather than the bytes.
            return response.data.text().then((text) => {
              const body = JSON.parse(text);
              const url = body?.data?.url || body?.url;
              if (url) {
                window.location.assign(url);
                this.finish();
                return;
              }
              throw new Error(body?.message || 'Download failed');
            });
          }
          this.saveBlob(response.data);
          this.finish();
        })
        .catch((err) => this.showError(err))
        .finally(() => { this.loading = false; });
    },

    saveBlob(blob) {
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = this.filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    },

    finish() {
      this.$emit('downloaded');
      this.close();
    },

    // Errors arrive as a blob because of responseType, so the JSON inside has
    // to be read back out before the message can be shown.
    showError(err) {
      const fallback = this.translations.downloadFailed_ || 'Download failed';
      const data = err?.response?.data;
      if (data instanceof Blob) {
        data.text()
          .then((text) => {
            try {
              this.error = JSON.parse(text)?.message || fallback;
            } catch (e) {
              this.error = fallback;
            }
          })
          .catch(() => { this.error = fallback; });
        return;
      }
      this.error = data?.message || fallback;
    },
  },

  template: `
    <v-dialog v-model="open" max-width="440" persistent>
      <v-card :loading="loading">
        <v-card-title class="d-flex align-center ga-2">
          <v-icon icon="mdi-shield-key-outline" color="primary"></v-icon>
          {{ title || translations.enterVerificationCode_ || 'Enter verification code' }}
        </v-card-title>

        <v-card-text>
          <p class="text-body-2 mb-4">
            {{ translations.downloadCodeHint_ ||
               'An admin was given a one-time code when they approved this download. Enter it to release the file.' }}
          </p>

          <v-text-field
            v-model="code"
            autofocus
            variant="outlined"
            density="comfortable"
            spellcheck="false"
            autocomplete="off"
            class="download-code-field"
            placeholder="XXXX-XXXX"
            :disabled="loading"
            :error-messages="error"
            @keydown.enter="submit"
          ></v-text-field>
        </v-card-text>

        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn variant="text" :disabled="loading" @click="close">
            {{ translations.cancel_ || 'Cancel' }}
          </v-btn>
          <v-btn color="primary" variant="flat" :loading="loading"
                 :disabled="!code.trim()" @click="submit">
            {{ translations.download_ || 'Download' }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  `,
});
