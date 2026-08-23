/**
 * DELIBERATELY UNWIRED — do not load or register this component.
 *
 * It displays a PDF by handing its URL to an <iframe>, which means the browser's
 * own PDF viewer renders it, complete with download and print buttons. Those
 * buttons act on bytes the browser already holds, so no server-side control can
 * take them away: wiring this component back in reopens a download path around
 * the approval flow in enferno/admin/views/download_requests.py.
 *
 * Use PdfViewer.js instead. It renders through PDF.js onto a canvas, so the file
 * is never handed to the browser's viewer.
 */
const NativePdfViewer = Vue.defineComponent({
  props: ['media', 'mediaType'],
  data: () => {
    return {
      translations: window.translations,
      fullscreen: false,
    };
  },
  methods: {
    requestFullscreen() {
      this.fullscreen = true;
    },
  },
  template: `
    <div>
      <v-dialog
        v-model="fullscreen"
        fullscreen
      >
        <v-card class="overflow-hidden">
          <v-toolbar color="dark-primary">
              <v-toolbar-title>{{ translations.preview_ }}</v-toolbar-title>
              <v-spacer></v-spacer>
          
              <template #append>
                  <v-btn icon="mdi-close" @click.stop.prevent="fullscreen = false"></v-btn>
              </template>
          </v-toolbar>
      
          <v-card-text class="pa-0" style="height: calc(100vh - 64px);">
            <iframe :src="media?.s3url" class="w-100 h-100" allow="fullscreen" allow-fullscreen></iframe>
          </v-card-text>
        </v-card>
      </v-dialog>

      <iframe :src="media?.s3url" class="w-100 h-100"   allowfullscreen allow-fullscreen></iframe>
    </div>
    `,
});
