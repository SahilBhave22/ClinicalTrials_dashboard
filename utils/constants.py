"""
Domain constants: phases, statuses, outcome categories, PRO instruments, etc.
"""

PHASES = ["EARLY_PHASE1", "PHASE1", "PHASE2", "PHASE3", "PHASE4"]

PHASE_LABELS = {
    "EARLY_PHASE1": "Early Phase 1",
    "PHASE1":       "Phase 1",
    "PHASE2":       "Phase 2",
    "PHASE3":       "Phase 3",
    "PHASE4":       "Phase 4",
}

STATUSES = [
    "COMPLETED",
    "RECRUITING",
    "ACTIVE_NOT_RECRUITING",
    "TERMINATED",
    "SUSPENDED",
    "WITHDRAWN",
    "UNKNOWN",
]

STATUS_LABELS = {
    "COMPLETED":             "Completed",
    "RECRUITING":            "Recruiting",
    "ACTIVE_NOT_RECRUITING": "Active (Not Recruiting)",
    "TERMINATED":            "Terminated",
    "SUSPENDED":             "Suspended",
    "WITHDRAWN":             "Withdrawn",
    "UNKNOWN":               "Unknown",
}

ACTIVE_STATUSES = {"RECRUITING", "ACTIVE_NOT_RECRUITING"}

OUTCOME_TYPES = ["Primary", "Secondary", "Other"]

OUTCOME_CATEGORIES = [
    "OS", "PFS", "ORR", "TTR", "TTP", "CR", "DOR",
    "DCR", "PR", "SD", "PD", "EFS", "RFS", "DFS",
    "PRO", "Safety", "PK", "Other",
]

DESIGN_OUTCOME_TYPES = ["primary", "secondary", "other"]

ALLOCATION_VALUES    = ["Randomized", "Non-Randomized", "N/A"]
INTERVENTION_MODELS  = ["Crossover", "Parallel", "Sequential", "Single Group", "Factorial"]
PRIMARY_PURPOSES     = ["Treatment", "Prevention", "Diagnostic", "Supportive Care",
                        "Screening", "Health Services Research", "Basic Science", "Other"]

AGENCY_CLASSES = {
    "INDUSTRY":   "Industry",
    "FED":        "Federal",
    "OTHER_GOV":  "Other Government",
    "INDIV":      "Individual",
    "NETWORK":    "Network",
    "NIH":        "NIH",
    "OTHER":      "Other",
}

# Baseline-like classification values to flag/exclude in score comparisons
BASELINE_CLASSIFICATIONS = {
    "baseline", "cycle 1 day 1", "week 1 day 1", "month 1 day 1",
    "day 1", "day 1 of cycle 1", "pre-dose", "pre-treatment",
    "screening", "baseline (day 1)",
}

# PRO instruments – display reference
COMMON_PRO_INSTRUMENTS = [
    "EQ-5D", "FACT-G", "FACT-L", "BFI", "EORTC QLQ-C30",
    "EORTC QLQ-LC13", "SF-36", "PROMIS", "PGIS", "PGIC",
    "NRS", "VAS", "MDASI", "HADS", "PHQ-9", "GAD-7",
]
