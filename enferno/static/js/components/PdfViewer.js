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
 * The watermark below exists for that reason: it puts the viewer's identity into
 * the rendered pixels, so a screenshot or a saved canvas carries it too.
 */
const PdfViewer = Vue.defineComponent({
  props: ['media', 'mediaType'],

  data: () => ({
    pageMap: new Map(),
    loading: false,
    error: false,
    // Fixed once per open so every page of one viewing carries one stamp.
    watermarkText: '',
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
    this.watermarkText = this.buildWatermark();
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

        // Drawn into the canvas itself, not overlaid in the DOM: a screenshot,
        // a "save image as" on the canvas, or a print all carry it, because by
        // this point it is part of the pixels rather than a element sitting on
        // top that could be hidden.
        this.drawWatermark(ctx, viewport.width, viewport.height);

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

    // Who is looking and when. Read from the server-rendered bootstrap rather
    // than anything the page could be tricked into changing.
    buildWatermark() {
      const user = window.__username__ || '';
      const now = new Date();
      const stamp = now.toISOString().slice(0, 16).replace('T', ' ') + ' UTC';
      return user ? `${user} · ${stamp}` : stamp;
    },

    drawWatermark(ctx, width, height) {
      const text = this.watermarkText;
      if (!text) return;

      ctx.save();
      // Light enough to read the document through, dark enough to survive a
      // screenshot being brightened.
      ctx.globalAlpha = 0.13;
      ctx.fillStyle = '#111';
      ctx.font = `${Math.max(12, Math.round(width / 42))}px sans-serif`;
      ctx.textBaseline = 'middle';
      ctx.rotate(-Math.PI / 6);

      const stepX = ctx.measureText(text).width + 70;
      const stepY = 95;
      // Rotating the plane means the tiling has to overshoot the page on every
      // side, otherwise corners come out bare.
      const span = width + height;
      for (let y = -span; y < span; y += stepY) {
        for (let x = -span; x < span; x += stepX) {
          ctx.fillText(text, x, y);
        }
      }
      ctx.restore();
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