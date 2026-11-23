// The classifier's fixed label set (backend/ingest/models.py ExpenseCategory).
export const CATEGORIES: [string, string][] = [
  ["software_subscriptions", "Software subscriptions"],
  ["hardware_equipment", "Hardware and equipment"],
  ["internet_phone", "Internet and phone"],
  ["office_rent_coworking", "Office rent / coworking"],
  ["business_travel", "Business travel"],
  ["professional_services", "Professional services"],
  ["bank_platform_fees", "Bank and platform fees"],
  ["training_books", "Training and books"],
  ["personal", "Personal (not business)"],
  ["tax_payment", "Tax payment"],
  ["own_transfer", "Transfer to own account"],
  ["uncertain", "Uncertain"],
];

export const CATEGORY_LABEL: Record<string, string> = Object.fromEntries(CATEGORIES);

// Below this the engine raises LOW_CLASSIFICATION_CONFIDENCE (flags.classification_confidence_min_percent).
export const CONFIDENCE_FLOOR = 0.8;
