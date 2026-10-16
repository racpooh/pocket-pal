# NOTE — r1 with REVISED ground truth (labels.v2, written after the model output was seen)
Same recorded outputs (20261016T110123Z); no model call; date-parser fix in place (validation 79dc61b1…).
Not comparable to a blind baseline: v2 corrected Thai text and one time against the images. bank_ref labels are still
the app name in v2 → excluded (n=0): reference accuracy is NOT measured for r1. Counterparty exact 4/5: the one
difference is a label that includes an extra printed line (shop description) beyond the name; "contains" match 5/5.
