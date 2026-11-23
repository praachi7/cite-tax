// Shown on every page (root layout). Wording follows the README's Disclaimer section.
export const DISCLAIMER =
  "CiteTax is an educational prototype. Its output is not legal or tax advice, has not been reviewed by a " +
  "chartered accountant or other professional, and should not be relied on for filing a return. It uses synthetic data only.";

// SRS/SDS 3.5 and NFR-4: the measured error rates beside the disclaimer. Copied from the held-out results in
// eval/results/phase_h_summary.json; backend/tests/test_disclaimer_figures.py fails if they drift apart.
export const MEASURED = {
  date: "23 Nov 2026",
  figures: "189/189",
  personas: "10",
  retrievalTop5: "29/32",
  wrongAct: "0",
  casesAsExpected: "29/31",
  falsePremiseMissed: "2/6",
  sentencesUnsupported: "9/35",
  checkerAccepted: "3/9",
};

const [missedPremises, premiseCases] = MEASURED.falsePremiseMissed.split("/");
const [unsupported, sentences] = MEASURED.sentencesUnsupported.split("/");
const [accepted] = MEASURED.checkerAccepted.split("/");

export const ERROR_RATES =
  `Measured ${MEASURED.date} on questions not used for tuning: tax figures ${MEASURED.figures} correct on ` +
  `${MEASURED.personas} test personas; the right passage in the top 5 for ${MEASURED.retrievalTop5} questions, ` +
  `${MEASURED.wrongAct} from the wrong Act; ${MEASURED.casesAsExpected} questions handled as expected, but ` +
  `${missedPremises} of ${premiseCases} false premises missed; ${unsupported} of ${sentences} answer sentences not ` +
  `fully supported by their citation, and the checker wrongly accepted ${accepted} of those.`;
