"""
Per-user access configuration.

Edit USER_ACCESS to control what each user can see and access.

Keys per user:
  display_name  : str — shown in the sidebar user badge

  ── Tab access (use ONE form, or omit both for all tabs) ──────────────────────
  tabs          : list of tab names to ALLOW  (inclusion mode)
  tabs_exclude  : list of tab names to REMOVE from the full list (exclusion mode)
                  If both are set, tabs (inclusion) wins.
                  Valid names (plain text, emojis optional):
                    Home, Ask the Data, Pipeline, Drug Detail, Drug Pricing,
                    Market Access, Sponsors, Trial Design, Endpoints, Outcomes,
                    Scores, PRO Overview, Trial Groups, Safety

  ── Disease area access (use ONE form, or omit both for all) ─────────────────
  disease_areas         : list of allowed disease bucket display labels  (inclusion mode)
  disease_areas_exclude : list of disease bucket display labels to REMOVE (exclusion mode)
                          If both are set, disease_areas (inclusion) wins.
                          Values must be display labels from catalogs/disease_bucket_mapping.json
                          (the JSON values, not the raw condition name keys).

  ── Drug class access (use ONE form, or omit both for all) ───────────────────
  drug_classes         : list of allowed ATC class names        (inclusion mode)
  drug_classes_exclude : list of ATC class names to REMOVE      (exclusion mode)
                         If both are set, drug_classes (inclusion) wins.
                         Values must match atc_class_name in the drugs database.
                         See catalogs/condition_sponsor_values.json for valid values.

Convention:
  None / key absent = no restriction (show everything)
  []                = deny all (user sees nothing — avoid this)
  [...]             = restricted to / excluding these values

To add a new user:
  1. Add an entry here under their username (must match the key in secrets.toml [users.*])
  2. Add their password to .streamlit/secrets.toml under [users.<username>]
"""

USER_ACCESS: dict[str, dict] = {
    "admin": {
        "display_name": "Administrator",
        "tabs":          None,
        "disease_areas": None,
        "drug_classes":  None,
    },
    "User1": {
        "display_name": "User1",
        "tabs": [
            "Home",
            "Pipeline",
            "Drug Detail",
            "Trial Design",
            "Outcomes",
        ],
        "disease_areas": ["Breast Cancer", "Lung Cancer"],
        "drug_classes":  None,
    },
    "sahil": {
        "display_name": "Sahil",
        "tabs": [
            "Home",
            "Drug Detail",
            "Sponsors",
            "Endpoints",
            "Outcomes",
            "Safety",
        ],
        "disease_areas": None,
        "drug_classes":  None,
    },
    "ambi": {
        "display_name": "Ambi",
        "tabs": None,
        "disease_areas": ["Atopic Dermatitis / Eczema", "Migraine", "Chronic Obstructive Pulmonary Disease"],
        "drug_classes":  None,
    },
    "User2": {
        "display_name": "User2",
        "tabs_exclude": ["Drug Pricing", "Market Access", "Scores","Trial Groups"],
        "disease_areas_exclude": ["Atopic Dermatitis / Eczema", "Migraine", "Chronic Obstructive Pulmonary Disease"],
        "drug_classes":  None,
    },
    "User3": {
        "display_name": "User3",
        "tabs_exclude": ['Drug Pricing', 'Market Access', 'Scores'],
        "disease_areas": ["Atopic Dermatitis / Eczema", "Migraine", "Chronic Obstructive Pulmonary Disease"],
        "drug_classes":  None,
    }
}
