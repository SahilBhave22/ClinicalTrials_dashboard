"""
Per-user access configuration.

Edit USER_ACCESS to control what each user can see and access.

Keys per user:
  display_name  : str — shown in the sidebar user badge
  tabs          : list of tab labels (must match PAGE_MAP labels in app.py), or None for all tabs
  disease_areas : list of allowed indication/disease area names, or None for no restriction
                  Values must match downcase_mesh_term values in the AACT database.
                  See catalogs/condition_sponsor_values.json for valid values.
  drug_classes  : list of allowed ATC class names, or None for no restriction
                  Values must match atc_class_name values in the drugs database.
                  See catalogs/condition_sponsor_values.json for valid values.

Convention:
  None   = no restriction (show everything)
  []     = deny all (user sees nothing — avoid this)
  [...]  = restricted to these values only

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
            "🏠 Home",
            "📈 Pipeline",
            "💊 Drug Detail",
            "📋 Trial Design",
            "📊 Outcomes",
        ],
        "disease_areas": ["breast neoplasms", "lung neoplasms"],
        "drug_classes":  None,
    },
    "sahil": {
        "display_name": "Sahil",
        "tabs": [
            "🏠 Home",
            "💊 Drug Detail",
            "🏢 Sponsors",
            "🎯 Endpoints",
            "📊 Outcomes",
            "🛡️ Safety",
        ],
        "disease_areas": None,
        "drug_classes":  None,
    },
    "carol": {
        "display_name": "Carol",
        "tabs": [
            "🏠 Home",
            "📈 Pipeline",
            "💊 Drug Detail",
            "📋 Trial Design",
            "📊 Outcomes",
        ],
        "disease_areas": ["colorectal neoplasms"],
        "drug_classes":  ["Fluoropyrimidines"],
    },
}
