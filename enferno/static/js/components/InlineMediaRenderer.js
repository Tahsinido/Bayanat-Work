const InlineMediaRenderer = Vue.defineComponent({
    props: {
      rendererId: {
        type: String,
      },
      media: {
        type: Object,
      },
      useMetadata: {
        type: Boolean,
      },
      mediaType: {
        type: String,
      },
      contentStyle: {
        type: String,
        default: 'height: 450px;'
      },
      hideClose: {
        type: Boolean,
        default: false
      },
      initialOrientation: {
        type: Number,
        default: 0,
      },
    },
    emits: ['ready', 'fullscreen', 'close', 'orientation-changed'],
    data: () => ({
      translations: window.translations,
      iconMap: {
        image: 'mdi-image',
        video: 'mdi-video',
        pdf: 'mdi-file-pdf-box',
        audio: 'mdi-music-box',
        docx: 'mdi-file-word-outline',
        unknown: 'mdi-file-download'
      },
    }),
    computed: {
      // Server-rendered flag; mirrors MediaCard so both offer the same path.
      downloadGated() {
        return window.__DOWNLOAD_APPROVAL__ !== false;
      },

    },
    methods: {
      emitReady() {
        this.$nextTick(() => {
          this.$emit('ready', {
            rendererId: this.rendererId,
            playerContainer:  this.$refs.playerContainer ?? null,
            requestFullscreen: this.requestFullscreen,
            scrollIntoView: (options) => {
              this.$refs.inlineMediaRenderer?.scrollIntoView?.(options);
            }
          });
        });
      },
      requestFullscreen() {
        if (this.mediaType === 'image') {
          this.$refs.imageViewer?.requestFullscreen?.();
        }

        if (this.mediaType === 'pdf') {
          this.$refs.pdfViewer?.requestFullscreen?.();
        }

        if (this.mediaType === 'docx') {
          this.$refs.docxViewer?.requestFullscreen?.();
        }
      }
    },
    watch: {
      media: {
        immediate: true,
        handler(nextMedia) {
          if (nextMedia) this.emitReady();
        },
      },
    },
    template: `
      <div ref="inlineMediaRenderer" v-if="media">
        <v-toolbar density="compact" class="px-2">
          <div v-if="useMetadata" class="w-100 d-flex justify-space-between align-center">
            <div class="d-flex align-center">
              <v-icon
                :icon="iconMap[mediaType]"
                :color="mediaType === 'pdf' ? 'red' : 'primary'"
              ></v-icon>
              <v-divider vertical class="mx-2"></v-divider>
              <v-chip prepend-icon="mdi-identifier" variant="text" class="font-weight-bold"
                >{{ media.id }}</v-chip
              >
              <v-divider vertical class="mx-2"></v-divider>
              <v-tooltip location="bottom">
                <template v-slot:activator="{ props }">
                  <v-chip
                    prepend-icon="mdi-tag"
                    variant="plain"
                    v-if="media.category"
                    size="small"
                    v-bind="props"
                  >
                    {{ media.category.title }}
                  </v-chip>
                </template>
                <span>{{ translations.category_ }}</span>
              </v-tooltip>
              <uni-field
                class="text-truncate"
                :english="media.title || 'Untitled'"
                :arabic="media.title_ar || ''"
                disable-spacing
              ></uni-field>
              <div v-if="media.filename" class="cursor-pointer">
                <v-list-item class="text-caption ml-1 py-0">
                  <template v-slot:prepend>
                    <v-tooltip location="bottom">
                      <template v-slot:activator="{ props }">
                        <v-icon v-bind="props" icon="mdi-file-outline"></v-icon>
                      </template>
                      <div class="d-flex flex-column align-center">
                        <span><strong>{{ translations.filename_ }}</strong></span>
                      </div>
                    </v-tooltip>
                  </template>
                  <v-tooltip location="bottom">
                    <template v-slot:activator="{ props }">
                      <div v-bind="props" class="text-truncate">{{ media.filename }}</div>
                    </template>
                    {{ media.filename }}
                  </v-tooltip>
                </v-list-item>
              </div>
              <div v-if="media.etag" class="d-flex align-center cursor-pointer">
                <v-list-item class="text-caption ml-1 py-0 text-truncate">
                  <template v-slot:prepend>
                    <v-tooltip location="bottom">
                      <template v-slot:activator="{ props }">
                        <v-icon v-bind="props" icon="mdi-fingerprint"></v-icon>
                      </template>
                      <div class="d-flex flex-column align-center">
                        <span><strong>{{ translations.etag_ }}</strong></span>
                      </div>
                    </v-tooltip>
                  </template>
                  <v-tooltip location="bottom">
                    <template v-slot:activator="{ props }">
                      <div v-bind="props" class="text-truncate">{{ media.etag }}</div>
                    </template>
                    {{ media.etag }}
                  </v-tooltip>
                </v-list-item>
              </div>
            </div>
          </div>
          <v-spacer></v-spacer>
          <!--
            Lives here rather than on each page's own toolbar so every viewer --
            bulletins, actors, incidents, field data, the media dashboard --
            offers the same one route to a copy of the file.
          -->
          <download-request-button
              v-if="media && media.id"
              :media="media"
              :gated="downloadGated"
              :direct-url="media.s3url"
          ></download-request-button>
          <v-btn @click="$emit('fullscreen')" icon="mdi-fullscreen" class="ml-2" size="small"></v-btn>
          <v-btn v-if="hideClose === false" icon="mdi-close" class="ml-2" size="small" @click="$emit('close')"></v-btn>
        </v-toolbar>

        <div :style="contentStyle">
          <div
            v-if="['video', 'audio'].includes(mediaType)"
            ref="playerContainer"
            class="h-100"
          ></div>
          <!--
            PDFs always render through PDF.js onto a canvas. Handing the file to
            the browser's built-in viewer (an <iframe src=...>) would come with
            its own download and print buttons, and those act on bytes the
            browser already holds -- nothing server-side can take them away.
            Rendering to canvas keeps the file out of the browser's viewer.
          -->
          <pdf-viewer ref="pdfViewer" v-else-if="mediaType === 'pdf'" :media="media" :media-type="mediaType" class="w-100 h-100"></pdf-viewer>
          <image-viewer ref="imageViewer" v-else-if="mediaType === 'image'" :initial-orientation="initialOrientation" :media="media" :media-type="mediaType" class="h-100" @orientation-changed="$emit('orientation-changed', $event)"></image-viewer>
          <docx-viewer ref="docxViewer" v-else-if="mediaType === 'docx'" :media="media" class="w-100 h-100"></docx-viewer>

          <!--
            Fallback for file types with no in-app renderer. There is no direct
            link here on purpose: a plain href to the file is the same bypass as
            the browser's PDF viewer. Getting a copy goes through the approval
            flow like every other download.
          -->
          <div v-else-if="mediaType === 'unknown'" class="h-100 d-flex flex-column align-center justify-center bg-grey-lighten-2">
            <v-icon size="64" color="grey">mdi-file-lock-outline</v-icon>
            <div class="text-h6 mt-4 text-medium-emphasis">{{ translations.previewNotAvailable_ }}</div>
            <div class="text-caption text-medium-emphasis">{{ media.filename }}</div>
            <download-request-button
              v-if="media && media.id"
              class="mt-4"
              :media="media"
              :gated="downloadGated"
              :direct-url="media.s3url"
            ></download-request-button>
          </div>
        </div>
      </div>
    `,
  });
  