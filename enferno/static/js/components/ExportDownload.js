const ExportDownload = Vue.defineComponent({
  props: {
    item: {},
  },
  data() {
    return {
      translations: window.translations,
      timer: null,
      status: this.item.status,
      codeOpen: false,
    };
  },

  watch: {
    'item.status'(newStatus) {
      this.status = newStatus;
      this.setupInterval();
    }
  },

  mounted() {
    this.setupInterval();
  },

  methods: {
    setupInterval() {
      if (this.status === 'Processing' && !this.timer) {
        const splitInterval = Math.random() * 5 + 3;
        this.timer = setInterval(this.checkStatus, splitInterval * 1000);
      }
    },

    checkStatus() {
      if (this.status === 'Ready') {
        clearInterval(this.timer);
        this.timer = null;
        this.$root.refresh();
        return;
      }
      axios
        .get(`/export/api/export/${this.item.id}`)
        .then((response) => {
          this.status = response.data.status;
        });
    },

    startDownload() {
      // The archive is only ever released in the response to a POST, so there
      // is no URL to leak. With approval on that POST carries the code the
      // admin issued; with it off the same POST just goes without one.
      if (this.item.code_required === false) {
        this.directDownload();
        return;
      }
      this.codeOpen = true;
    },

    directDownload() {
      axios
        .post('/export/api/exports/download', { exportId: this.item.uid }, {
          responseType: 'blob',
          suppressGlobalErrorHandler: true,
        })
        .then((response) => {
          const url = window.URL.createObjectURL(response.data);
          const link = document.createElement('a');
          link.href = url;
          link.download = `export-${this.item.id}.zip`;
          document.body.appendChild(link);
          link.click();
          document.body.removeChild(link);
          window.URL.revokeObjectURL(url);
        })
        .catch(() => {
          this.$root.showSnack?.(this.translations.downloadFailed_ || 'Download failed');
        });
    },

    onDownloaded() {
      this.$root.refresh?.();
    },
  },
  template: `

          <div>
            <v-progress-circular v-if="status === 'Processing'"
                                 indeterminate
                                 :size="16"
                                 width="2"
                                 color="primary"
            ></v-progress-circular>
            <v-tooltip :text="status">
            <template #activator="{props}">
            <v-icon 
                    v-if="status==='Pending'">mdi-clock-time-eleven-outline v-bind="props"
            </v-icon>

            <v-icon 
                    v-if="status==='Rejected'" color="error">mdi-cancel v-bind="props"
            </v-icon>
            <v-icon 
                    v-if="status==='Failed'" color="error">mdi-alert-circle v-bind="props"
            </v-icon>
            <v-icon 
                    v-if="status==='Expired'"
                    color="grey">mdi-close-circle
                    v-bind="props"
            </v-icon>
            </template>
            </v-tooltip>
            <v-tooltip location="top" :text="translations.download_">
            <template #activator="{props}">
            <v-btn @click.stop="startDownload"
                  v-bind="props"
                   variant="text"
                   v-if="status === 'Ready'" icon="mdi-download-circle" color="success">
            </v-btn>
            </template>
            </v-tooltip>

            <download-code-dialog
                v-model="codeOpen"
                url="/export/api/exports/download"
                :payload="{ exportId: item.uid }"
                :filename="'export-' + item.id + '.zip'"
                @downloaded="onDownloaded"
            ></download-code-dialog>

      </div>

    `,
});
