/**
 * Shows an approving admin the one-time code, once.
 *
 * The server stores only a hash, so this is genuinely the only moment the code
 * exists in readable form — the dialog says so plainly, because an admin who
 * dismisses it expecting to find the code later will have to approve again.
 *
 * The code is meant to leave on a different channel from the session that will
 * use it: spoken, or sent over whatever the team already trusts.
 */
const IssuedCodeDialog = Vue.defineComponent({
  props: {
    modelValue: { type: Boolean, default: false },
    code: { type: String, default: '' },
    // Who should receive it, so the admin knows who to contact.
    recipient: { type: String, default: '' },
  },
  emits: ['update:modelValue'],

  data() {
    return {
      translations: window.translations || {},
      copied: false,
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
      if (isOpen) this.copied = false;
    },
  },

  methods: {
    copy() {
      if (!navigator.clipboard) return;
      navigator.clipboard.writeText(this.code).then(() => {
        this.copied = true;
        setTimeout(() => { this.copied = false; }, 2000);
      }).catch(() => { /* clipboard blocked; the code is on screen regardless */ });
    },
  },

  template: `
    <v-dialog v-model="open" max-width="460" persistent>
      <v-card>
        <v-card-title class="d-flex align-center ga-2">
          <v-icon icon="mdi-shield-key" color="success"></v-icon>
          {{ translations.downloadApproved_ || 'Download approved' }}
        </v-card-title>

        <v-card-text>
          <p class="text-body-2 mb-4">
            <template v-if="recipient">
              {{ translations.giveCodeTo_ || 'Give this code to' }} <strong>{{ recipient }}</strong>
              {{ translations.directly_ || 'directly' }}.
            </template>
            <template v-else>
              {{ translations.giveCodeToRequester_ || 'Give this code to the requester directly.' }}
            </template>
          </p>

          <v-sheet border rounded class="pa-4 text-center mb-3">
            <div class="text-h4 font-weight-bold download-code-display">{{ code }}</div>
          </v-sheet>

          <v-btn block variant="tonal" :color="copied ? 'success' : 'primary'"
                 :prepend-icon="copied ? 'mdi-check' : 'mdi-content-copy'"
                 @click="copy">
            {{ copied ? (translations.copied_ || 'Copied') : (translations.copyCode_ || 'Copy code') }}
          </v-btn>

          <v-alert type="warning" variant="tonal" density="compact" class="mt-4">
            {{ translations.codeShownOnce_ ||
               'This code is shown once and cannot be recovered. Send it over a channel separate from this system.' }}
          </v-alert>
        </v-card-text>

        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn color="primary" variant="flat" @click="open = false">
            {{ translations.done_ || 'Done' }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  `,
});
