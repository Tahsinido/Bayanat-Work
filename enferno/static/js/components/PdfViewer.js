/**
 * In-app PDF viewer, rendered with PDF.js onto a canvas.
 *
 * The file is never handed to the browser's own PDF viewer, so its Download and
 * Print buttons never appear. It is fetched from /admin/api/media/<id>/proxy,
 * which keeps Bayanat's authentication and permission checks in front of the
 * bytes and never exposes the document at a public or static URL -- on S3
 * deployments the proxy streams the file server-side rather than handing the
 * browser a presigned link.
 *
 * DETERRENT, NOT DRM. Hiding Download and Print raises the effort required; it
 * does not make the document uncopyable. Anyone who can see the page can still
 * screenshot it, and the decoded bytes exist in the browser by necessity --
 * devtools' network tab still shows the proxy response. Treat this as a control
 * against casual redistribution and an aid to accountability, never as a
 * guarantee that a viewer cannot retain a copy.
 *
 * Nothing is drawn over the document. What is shown here is the original file
 * exactly as it is stored: no watermark, no viewer name, no date. The
 * organisation stamp belongs only on a copy that leaves the system, which is
 * applied server-side at download time -- see enferno/utils/watermark.py.
 *
 * Accountability is carried by the access log instead: every read through the
 * proxy is recorded as an Activity against the user who made it.
 */
const PdfViewer = Vue.defineComponent({
  props: ['media', 'mediaType'],

  data: () => ({
    pageMap: new Map(),
    loading: false,
    error: false,
  }),

  computed: {
    src() {
      return this.media?.id ? `/admin/api/media/${this.media.id}/proxy` : null;
    },
  },

  watch: {
    src: {
      immediate: true,
      async handler(url) {
        if (url) await this.loadPdf(url);
      },
    },
  },

  created() {
    this._pdf = null;               // non-reactive PDFDocumentProxy
    this._rendering = new Set();    // guard against double render
  },

  beforeUnmount() {
    this._pdf?.destroy?.();
    this._pdf = null;
  },

  methods: {
    async loadPdf(url) {
      this.loading = true;
      this.error = false;
      this.pageMap = new Map();

      if (this._pdf) {
        try { await this._pdf.destroy(); } catch {}
        this._pdf = null;
      }

      try {
        await loadScript('/static/js/pdf.js/pdf.min.mjs');
        pdfjsLib.GlobalWorkerOptions.workerSrc = '/static/js/pdf.js/pdf.worker.min.mjs';

        const pdf = await pdfjsLib.getDocument(url).promise;
        this._pdf = pdf;

        // Use page 1 dimensions as the aspect ratio placeholder for all pages
        const firstPage = await pdf.getPage(1);
        const firstVp = firstPage.getViewport({ scale: 1 });
        const ratioWidth = firstVp.width;
        const ratioHeight = firstVp.height;
        await firstPage.cleanup();

        for (let i = 1; i <= pdf.numPages; i++) {
          this.pageMap.set(i, {
            pageNumber: i,
            width: ratioWidth,
            height: ratioHeight,
            rendered: false,
            renderError: false,
          });
        }
      } catch (e) {
        console.error('PDF load error:', e);
        this.error = true;
      } finally {
        this.loading = false;
      }
    },

    getCanvasEl(pageNumber) {
      // With v-for + :ref, Vue may store refs as arrays
      const ref = this.$refs[`pageCanvas-${pageNumber}`];
      return Array.isArray(ref) ? ref[0] : ref;
    },

    async renderPage(pageNumber) {
      if (this._rendering.has(pageNumber)) return;

      const pageState = this.pageMap.get(pageNumber);
      if (!pageState || pageState.rendered || pageState.renderError) return;
      if (!this._pdf) return;

      const canvas = this.getCanvasEl(pageNumber);
      if (!canvas) return; // not in DOM (scrolled away / destroyed)

      this._rendering.add(pageNumber);

      try {
        const page = await this._pdf.getPage(pageNumber);

        const scale = 1.5;
        const viewport = page.getViewport({ scale });

        // HiDPI support
        const dpr = window.devicePixelRatio || 1;

        // Size canvas backing store in physical pixels
        canvas.width = Math.floor(viewport.width * dpr);
        canvas.height = Math.floor(viewport.height * dpr);

        // Size canvas element in CSS pixels
        canvas.style.width = '100%';
        canvas.style.height = 'auto';

        const ctx = canvas.getContext('2d', { alpha: false });

        // Reset transform then scale for DPR
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

        // Fill white BEFORE rendering to prevent black flash on canvas resize
        ctx.fillStyle = '#fff';
        ctx.fillRect(0, 0, viewport.width, viewport.height);

        await page.render({ canvasContext: ctx, viewport }).promise;

        // Nothing is drawn after the page: what lands on the canvas is the
        // document as stored.

        // Update to actual rendered dimensions and mark as done
        this.pageMap.set(pageNumber, {
          ...pageState,
          width: viewport.width,
          height: viewport.height,
          rendered: true,
        });

        await page.cleanup();
      } catch (e) {
        console.error('Page render error:', e);
        this.pageMap.set(pageNumber, { ...pageState, renderError: true });
      } finally {
        this._rendering.delete(pageNumber);
      }
    },

    onIntersect(isIntersecting, entries, observer, page) {
      if (isIntersecting && !page.rendered && !page.renderError) {
        this.renderPage(page.pageNumber);
      }
    },

    requestFullscreen() {
      this.$refs.container?.requestFullscreen?.();
    },
  },

  template: `
    <div ref="container" class="pdf-viewer w-100 h-100 overflow-y-auto d-flex flex-column align-center bg-grey-lighten-3 pa-4 ga-4">

      <v-progress-circular
        v-if="loading"
        indeterminate
        color="primary"
        size="64"
        class="mt-8"
      ></v-progress-circular>

      <div v-else-if="error" class="d-flex flex-column align-center justify-center h-100 text-medium-emphasis">
        <v-icon size="64" color="red">mdi-file-pdf-box</v-icon>
        <div class="mt-2 text-caption">Failed to load PDF</div>
      </div>

      <div v-else v-for="page in Array.from(pageMap.values())" :key="page.pageNumber" class="w-100 d-flex justify-center">
        <div
          class="w-100 bg-white elevation-2 rounded overflow-hidden"
          style="max-width: 900px;"
          v-intersect="(isIntersecting, entries, observer) => onIntersect(isIntersecting, entries, observer, page)"
          :style="{ aspectRatio: page.width + ' / ' + page.height }"
        >
          <div v-if="page.renderError" class="pa-6 d-flex flex-column align-center justify-center">
            <v-icon size="48" color="red">mdi-alert-circle</v-icon>
            <div class="mt-2 text-caption">Failed to render page</div>
          </div>

          <template v-else>
            <!--
              Canvas is always in the DOM so the ref is available when
              onIntersect fires. It stays hidden (via opacity) until rendered
              to avoid the black flash from an unpainted canvas backing store.
            -->
            <canvas
              :ref="'pageCanvas-' + page.pageNumber"
              class="w-100"
              :style="{
                display: 'block',
                background: '#fff',
                opacity: page.rendered ? 1 : 0,
                position: page.rendered ? 'static' : 'absolute',
              }"
            ></canvas>

            <!-- Skeleton placeholder shown until the page is painted -->
            <div v-if="!page.rendered" class="pa-4">
              <v-skeleton-loader type="article, paragraph, paragraph"></v-skeleton-loader>
            </div>
          </template>
        </div>
      </div>
    </div>
  `,
});