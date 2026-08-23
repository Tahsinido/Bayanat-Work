from enferno.extensions import db

# joint table
bulletin_sources = db.Table(
    "bulletin_sources",
    db.Column("source_id", db.Integer, db.ForeignKey("source.id"), primary_key=True),
    db.Column("bulletin_id", db.Integer, db.ForeignKey("bulletin.id"), primary_key=True),
    db.Index("ix_bulletin_sources_source_id", "source_id"),
    db.Index("ix_bulletin_sources_bulletin_id", "bulletin_id"),
    extend_existing=True,
)

# joint table
bulletin_locations = db.Table(
    "bulletin_locations",
    db.Column("location_id", db.Integer, db.ForeignKey("location.id"), primary_key=True),
    db.Column("bulletin_id", db.Integer, db.ForeignKey("bulletin.id"), primary_key=True),
    db.Index("ix_bulletin_locations_location_id", "location_id"),
    db.Index("ix_bulletin_locations_bulletin_id", "bulletin_id"),
    extend_existing=True,
)

# joint table
bulletin_labels = db.Table(
    "bulletin_labels",
    db.Column("label_id", db.Integer, db.ForeignKey("label.id"), primary_key=True),
    db.Column("bulletin_id", db.Integer, db.ForeignKey("bulletin.id"), primary_key=True),
    db.Index("ix_bulletin_labels_label_id", "label_id"),
    db.Index("ix_bulletin_labels_bulletin_id", "bulletin_id"),
    extend_existing=True,
)

# joint table
bulletin_verlabels = db.Table(
    "bulletin_verlabels",
    db.Column("label_id", db.Integer, db.ForeignKey("label.id"), primary_key=True),
    db.Column("bulletin_id", db.Integer, db.ForeignKey("bulletin.id"), primary_key=True),
    db.Index("ix_bulletin_verlabels_label_id", "label_id"),
    db.Index("ix_bulletin_verlabels_bulletin_id", "bulletin_id"),
    extend_existing=True,
)

# joint table
bulletin_events = db.Table(
    "bulletin_events",
    db.Column("event_id", db.Integer, db.ForeignKey("event.id"), primary_key=True),
    db.Column("bulletin_id", db.Integer, db.ForeignKey("bulletin.id"), primary_key=True),
    db.Index("ix_bulletin_events_event_id", "event_id"),
    db.Index("ix_bulletin_events_bulletin_id", "bulletin_id"),
    extend_existing=True,
)

# joint table
bulletin_roles = db.Table(
    "bulletin_roles",
    db.Column("role_id", db.Integer, db.ForeignKey("role.id"), primary_key=True),
    db.Column("bulletin_id", db.Integer, db.ForeignKey("bulletin.id"), primary_key=True),
    db.Index("ix_bulletin_roles_role_id", "role_id"),
    db.Index("ix_bulletin_roles_bulletin_id", "bulletin_id"),
    extend_existing=True,
)

# Updated joint table for actor_sources
actor_sources = db.Table(
    "actor_sources",
    db.Column("source_id", db.Integer, db.ForeignKey("source.id"), primary_key=True),
    db.Column(
        "actor_profile_id",
        db.Integer,
        db.ForeignKey("actor_profile.id"),
        primary_key=True,
    ),
    db.Index("ix_actor_sources_source_id", "source_id"),
    db.Index("ix_actor_sources_actor_profile_id", "actor_profile_id"),
    extend_existing=True,
)

# joint table for actor_labels
actor_labels = db.Table(
    "actor_labels",
    db.Column("label_id", db.Integer, db.ForeignKey("label.id"), primary_key=True),
    db.Column(
        "actor_profile_id",
        db.Integer,
        db.ForeignKey("actor_profile.id"),
        primary_key=True,
    ),
    db.Index("ix_actor_labels_label_id", "label_id"),
    db.Index("ix_actor_labels_actor_profile_id", "actor_profile_id"),
    extend_existing=True,
)

# joint table for actor_verlabels
actor_verlabels = db.Table(
    "actor_verlabels",
    db.Column("label_id", db.Integer, db.ForeignKey("label.id"), primary_key=True),
    db.Column(
        "actor_profile_id",
        db.Integer,
        db.ForeignKey("actor_profile.id"),
        primary_key=True,
    ),
    db.Index("ix_actor_verlabels_label_id", "label_id"),
    db.Index("ix_actor_verlabels_actor_profile_id", "actor_profile_id"),
    extend_existing=True,
)


# joint table
actor_events = db.Table(
    "actor_events",
    db.Column("event_id", db.Integer, db.ForeignKey("event.id"), primary_key=True),
    db.Column("actor_id", db.Integer, db.ForeignKey("actor.id"), primary_key=True),
    db.Index("ix_actor_events_event_id", "event_id"),
    db.Index("ix_actor_events_actor_id", "actor_id"),
    extend_existing=True,
)

# joint table
actor_roles = db.Table(
    "actor_roles",
    db.Column("role_id", db.Integer, db.ForeignKey("role.id"), primary_key=True),
    db.Column("actor_id", db.Integer, db.ForeignKey("actor.id"), primary_key=True),
    db.Index("ix_actor_roles_role_id", "role_id"),
    db.Index("ix_actor_roles_actor_id", "actor_id"),
    extend_existing=True,
)

actor_countries = db.Table(
    "actor_countries",
    db.Column("actor_id", db.Integer, db.ForeignKey("actor.id"), primary_key=True),
    db.Column("country_id", db.Integer, db.ForeignKey("countries.id"), primary_key=True),
    extend_existing=True,
)

actor_ethnographies = db.Table(
    "actor_ethnographies",
    db.Column("actor_id", db.Integer, db.ForeignKey("actor.id"), primary_key=True),
    db.Column("ethnography_id", db.Integer, db.ForeignKey("ethnographies.id"), primary_key=True),
    extend_existing=True,
)

actor_dialects = db.Table(
    "actor_dialects",
    db.Column("actor_id", db.Integer, db.ForeignKey("actor.id"), primary_key=True),
    db.Column("dialect_id", db.Integer, db.ForeignKey("dialects.id"), primary_key=True),
    extend_existing=True,
)


# joint table
incident_locations = db.Table(
    "incident_locations",
    db.Column("location_id", db.Integer, db.ForeignKey("location.id"), primary_key=True),
    db.Column("incident_id", db.Integer, db.ForeignKey("incident.id"), primary_key=True),
    db.Index("ix_incident_locations_location_id", "location_id"),
    db.Index("ix_incident_locations_incident_id", "incident_id"),
    extend_existing=True,
)

# joint table
incident_labels = db.Table(
    "incident_labels",
    db.Column("label_id", db.Integer, db.ForeignKey("label.id"), primary_key=True),
    db.Column("incident_id", db.Integer, db.ForeignKey("incident.id"), primary_key=True),
    db.Index("ix_incident_labels_label_id", "label_id"),
    db.Index("ix_incident_labels_incident_id", "incident_id"),
    extend_existing=True,
)

# joint table
incident_events = db.Table(
    "incident_events",
    db.Column("event_id", db.Integer, db.ForeignKey("event.id"), primary_key=True),
    db.Column("incident_id", db.Integer, db.ForeignKey("incident.id"), primary_key=True),
    db.Index("ix_incident_events_event_id", "event_id"),
    db.Index("ix_incident_events_incident_id", "incident_id"),
    extend_existing=True,
)

# joint table
incident_potential_violations = db.Table(
    "incident_potential_violations",
    db.Column(
        "potentialviolation_id",
        db.Integer,
        db.ForeignKey("potential_violation.id"),
        primary_key=True,
    ),
    db.Column("incident_id", db.Integer, db.ForeignKey("incident.id"), primary_key=True),
    db.Index("ix_incident_potential_violations_potentialviolation_id", "potentialviolation_id"),
    db.Index("ix_incident_potential_violations_incident_id", "incident_id"),
    extend_existing=True,
)

# joint table
incident_claimed_violations = db.Table(
    "incident_claimed_violations",
    db.Column(
        "claimedviolation_id", db.Integer, db.ForeignKey("claimed_violation.id"), primary_key=True
    ),
    db.Column("incident_id", db.Integer, db.ForeignKey("incident.id"), primary_key=True),
    db.Index("ix_incident_claimed_violations_claimedviolation_id", "claimedviolation_id"),
    db.Index("ix_incident_claimed_violations_incident_id", "incident_id"),
    extend_existing=True,
)

# joint table
incident_roles = db.Table(
    "incident_roles",
    db.Column("role_id", db.Integer, db.ForeignKey("role.id"), primary_key=True),
    db.Column("incident_id", db.Integer, db.ForeignKey("incident.id"), primary_key=True),
    db.Index("ix_incident_roles_role_id", "role_id"),
    db.Index("ix_incident_roles_incident_id", "incident_id"),
    extend_existing=True,
)

# joint table
field_data_locations = db.Table(
    "field_data_locations",
    db.Column("location_id", db.Integer, db.ForeignKey("location.id"), primary_key=True),
    db.Column("field_data_id", db.Integer, db.ForeignKey("field_data.id"), primary_key=True),
    db.Index("ix_field_data_locations_location_id", "location_id"),
    db.Index("ix_field_data_locations_field_data_id", "field_data_id"),
    extend_existing=True,
)

# ---------------------------------------------------------------------------
# Evidence joint tables
#
# Evidence reuses Bayanat's existing vocabulary -- locations, sources, events,
# actors, bulletins -- rather than carrying parallel free-text copies, so an
# evidence record filed against a location is searchable alongside every other
# record at that location.
# ---------------------------------------------------------------------------

# joint table: evidence <-> access-control roles
evidence_roles = db.Table(
    "evidence_roles",
    db.Column("evidence_id", db.Integer, db.ForeignKey("evidence.id"), primary_key=True),
    db.Column("role_id", db.Integer, db.ForeignKey("role.id"), primary_key=True),
    db.Index("ix_evidence_roles_evidence_id", "evidence_id"),
    db.Index("ix_evidence_roles_role_id", "role_id"),
    extend_existing=True,
)

# joint table: the Case/Bulletin an evidence item belongs to
evidence_bulletins = db.Table(
    "evidence_bulletins",
    db.Column("evidence_id", db.Integer, db.ForeignKey("evidence.id"), primary_key=True),
    db.Column("bulletin_id", db.Integer, db.ForeignKey("bulletin.id"), primary_key=True),
    db.Index("ix_evidence_bulletins_evidence_id", "evidence_id"),
    db.Index("ix_evidence_bulletins_bulletin_id", "bulletin_id"),
    extend_existing=True,
)

# joint table: persons/sources associated with the evidence
evidence_actors = db.Table(
    "evidence_actors",
    db.Column("evidence_id", db.Integer, db.ForeignKey("evidence.id"), primary_key=True),
    db.Column("actor_id", db.Integer, db.ForeignKey("actor.id"), primary_key=True),
    db.Index("ix_evidence_actors_evidence_id", "evidence_id"),
    db.Index("ix_evidence_actors_actor_id", "actor_id"),
    extend_existing=True,
)

# joint table: relevant locations
evidence_locations = db.Table(
    "evidence_locations",
    db.Column("evidence_id", db.Integer, db.ForeignKey("evidence.id"), primary_key=True),
    db.Column("location_id", db.Integer, db.ForeignKey("location.id"), primary_key=True),
    db.Index("ix_evidence_locations_evidence_id", "evidence_id"),
    db.Index("ix_evidence_locations_location_id", "location_id"),
    extend_existing=True,
)

# joint table: relevant events
evidence_events = db.Table(
    "evidence_events",
    db.Column("evidence_id", db.Integer, db.ForeignKey("evidence.id"), primary_key=True),
    db.Column("event_id", db.Integer, db.ForeignKey("event.id"), primary_key=True),
    db.Index("ix_evidence_events_evidence_id", "evidence_id"),
    db.Index("ix_evidence_events_event_id", "event_id"),
    extend_existing=True,
)

# joint table: source information held as structured sources
evidence_sources = db.Table(
    "evidence_sources",
    db.Column("evidence_id", db.Integer, db.ForeignKey("evidence.id"), primary_key=True),
    db.Column("source_id", db.Integer, db.ForeignKey("source.id"), primary_key=True),
    db.Index("ix_evidence_sources_evidence_id", "evidence_id"),
    db.Index("ix_evidence_sources_source_id", "source_id"),
    extend_existing=True,
)

# joint table: "related records" -- evidence linked to other evidence. Ordered
# pair so the relationship can be read from either side.
evidence_related = db.Table(
    "evidence_related",
    db.Column("evidence_id", db.Integer, db.ForeignKey("evidence.id"), primary_key=True),
    db.Column("related_evidence_id", db.Integer, db.ForeignKey("evidence.id"), primary_key=True),
    db.Index("ix_evidence_related_evidence_id", "evidence_id"),
    db.Index("ix_evidence_related_related_id", "related_evidence_id"),
    extend_existing=True,
)


# ----------------------------------------------------------------------
# Eyewitness capture records
#
# An eyewitness record is the metadata a capture app hands over: who recorded
# it, on what device, when and where. It links outward to the entities Bayanat
# already holds rather than restating them, which is the point of the section --
# the same perpetrator, event or location is described once and referenced from
# every capture that touches it.
# ----------------------------------------------------------------------

# joint table: eyewitness <-> access-control roles
eyewitness_roles = db.Table(
    "eyewitness_roles",
    db.Column("eyewitness_id", db.Integer, db.ForeignKey("eyewitness.id"), primary_key=True),
    db.Column("role_id", db.Integer, db.ForeignKey("role.id"), primary_key=True),
    db.Index("ix_eyewitness_roles_eyewitness_id", "eyewitness_id"),
    db.Index("ix_eyewitness_roles_role_id", "role_id"),
    extend_existing=True,
)

# joint table: the Case/Bulletin a capture belongs to
eyewitness_bulletins = db.Table(
    "eyewitness_bulletins",
    db.Column("eyewitness_id", db.Integer, db.ForeignKey("eyewitness.id"), primary_key=True),
    db.Column("bulletin_id", db.Integer, db.ForeignKey("bulletin.id"), primary_key=True),
    db.Index("ix_eyewitness_bulletins_eyewitness_id", "eyewitness_id"),
    db.Index("ix_eyewitness_bulletins_bulletin_id", "bulletin_id"),
    extend_existing=True,
)

# joint table: alleged perpetrators, held as actors
eyewitness_actors = db.Table(
    "eyewitness_actors",
    db.Column("eyewitness_id", db.Integer, db.ForeignKey("eyewitness.id"), primary_key=True),
    db.Column("actor_id", db.Integer, db.ForeignKey("actor.id"), primary_key=True),
    db.Index("ix_eyewitness_actors_eyewitness_id", "eyewitness_id"),
    db.Index("ix_eyewitness_actors_actor_id", "actor_id"),
    extend_existing=True,
)

# joint table: "tags used", held as the same labels the rest of Bayanat uses so
# a tag typed on a phone is the same tag the archive already knows
eyewitness_labels = db.Table(
    "eyewitness_labels",
    db.Column("eyewitness_id", db.Integer, db.ForeignKey("eyewitness.id"), primary_key=True),
    db.Column("label_id", db.Integer, db.ForeignKey("label.id"), primary_key=True),
    db.Index("ix_eyewitness_labels_eyewitness_id", "eyewitness_id"),
    db.Index("ix_eyewitness_labels_label_id", "label_id"),
    extend_existing=True,
)

# joint table: the evidence items this capture produced, so the exhibit's own
# metadata never has to be retyped onto the capture
eyewitness_evidence = db.Table(
    "eyewitness_evidence",
    db.Column("eyewitness_id", db.Integer, db.ForeignKey("eyewitness.id"), primary_key=True),
    db.Column("evidence_id", db.Integer, db.ForeignKey("evidence.id"), primary_key=True),
    db.Index("ix_eyewitness_evidence_eyewitness_id", "eyewitness_id"),
    db.Index("ix_eyewitness_evidence_evidence_id", "evidence_id"),
    extend_existing=True,
)


# joint table: the field-data site visit a capture came out of, so a mission's
# own record of what was collected and a capture of it are two views of one
# thing rather than two sets of retyped metadata
eyewitness_field_data = db.Table(
    "eyewitness_field_data",
    db.Column("eyewitness_id", db.Integer, db.ForeignKey("eyewitness.id"), primary_key=True),
    db.Column("field_data_id", db.Integer, db.ForeignKey("field_data.id"), primary_key=True),
    db.Index("ix_eyewitness_field_data_eyewitness_id", "eyewitness_id"),
    db.Index("ix_eyewitness_field_data_field_data_id", "field_data_id"),
    extend_existing=True,
)
