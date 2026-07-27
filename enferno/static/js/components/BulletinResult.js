const BulletinResult = Vue.defineComponent({
  props: ['bulletin', 'hidden', 'showHide'],

  data: () => {
    return {
      translations: window.translations,
      hide: this.hidden || false,
    }
  },

  template: `
    <template v-if="!hide">
      <v-card v-if="!bulletin.restricted" hover class="ma-2">
        <v-toolbar density="compact" class="d-flex px-2">
          <v-chip color="primary" variant="flat" size="small">{{ translations.id_ }} {{ bulletin.id }}</v-chip>
          <v-chip v-if="bulletin.originid" variant="text" :href="bulletin.source_link" target="_blank" class="white--text ml-1" label
                  size="small"># {{ bulletin.originid }}
          </v-chip>
          <v-spacer></v-spacer>
          <v-chip variant="text" v-if="bulletin.publish_date" size="small">{{ $root.formatDate(bulletin.publish_date) }}</v-chip>
        </v-toolbar>
        <v-card-title class="text-wrap text-break pt-0">
          <uni-field class="pa-0" disable-spacing :caption="translations.originalTitle_" :english="bulletin.title" :arabic="bulletin.title_ar"></uni-field>
          <uni-field class="pa-0" disable-spacing :caption="translations.title_" :english="bulletin.sjac_title" :arabic="bulletin.sjac_title_ar"></uni-field>
        </v-card-title>
        <v-divider></v-divider>
        <slot name="header"></slot>

        <!-- Keyword in context: where the search term was found, with the
             surrounding lines, so the card can be judged without opening it. -->
        <v-card-text v-if="bulletin.snippet" class="py-2">
          <div class="text-caption text-medium-emphasis font-weight-medium">
            {{ bulletin.snippet.field }}
            <span class="text-disabled">({{ translations.line_ || 'line' }} {{ bulletin.snippet.line_number }})</span>
          </div>
          <div v-for="(l, i) in bulletin.snippet.before" :key="'sb'+i"
               class="text-caption text-disabled snippet-line">{{ l }}</div>
          <div class="text-body-2 snippet-line"><span>{{ bulletin.snippet.line_before }}</span><mark
              class="snippet-mark">{{ bulletin.snippet.match }}</mark><span>{{ bulletin.snippet.line_after }}</span></div>
          <div v-for="(l, i) in bulletin.snippet.after" :key="'sa'+i"
               class="text-caption text-disabled snippet-line">{{ l }}</div>
        </v-card-text>

        <v-card-text v-if="bulletin.locations?.length || bulletin.sources?.length">
              <v-list-item v-if="bulletin.locations?.length" :title="translations.locations_">
                <v-list-item-subtitle opacity="1">
                  <div class="flex-chips">
                    <v-chip label size="small" prepend-icon="mdi-map-marker" class="flex-chip" v-for="location in bulletin.locations" :key="location">
                      {{ location.full_string }}
                    </v-chip>
                  </div>
                </v-list-item-subtitle>
              </v-list-item>


              <v-list-item v-if="bulletin.sources?.length" :title="translations.sources_">
                <v-list-item-subtitle>
                  <div class="flex-chips">
                    <v-chip size="small" color="grey" class="flex-chip" v-for="source in bulletin.sources" :key="source">
                      {{ source.title }}
                    </v-chip>
                  </div>
                </v-list-item-subtitle>

              </v-list-item>
        </v-card-text>
        
        <v-card-actions class="justify-end">
          <slot name="actions"></slot>
          <v-tooltip location="bottom">
            <template v-slot:activator="{ props }">
              <v-btn
                v-bind="props"
                @click.capture="$root.previewItem('/admin/api/bulletin/'+bulletin.id+'?mode=3')"
                color="secondary"
                variant="outlined"
                icon="mdi-magnify-expand"
                size="small"
              ></v-btn>
            </template>
            {{ translations.preview_ }}
          </v-tooltip>
          <v-tooltip v-if="showHide" location="bottom">
            <template v-slot:activator="{ props }">
              <v-btn
                v-bind="props"
                @click="hide=true"
                color="secondary"
                variant="outlined"
                icon="mdi-minus"
                size="small"
              ></v-btn>
            </template>
            {{ translations.hideFromResults_ }}
          </v-tooltip>
        </v-card-actions>
      </v-card>

      <v-card disabled elevation="0" v-else class="restricted">

        <v-card-text>{{ bulletin.id }} - {{ translations.restricted_ }}</v-card-text>

      </v-card>
    </template>
  `,
});
