"""Phase E: transaction ingestion, receipt-mode tagging, synthetic data and rule-based expense classification.

The boundary with the tax engine is one function, receipt_mode.receipts_for_engine, which reads receipt
rows only. Expense classification feeds the actual-profit comparison and the evidence trail and is never
an input to the engine, so it cannot change presumptive income (s.44ADA(2); s.58(4) of the 2025 Act).
"""
