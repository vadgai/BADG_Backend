"""
Direct test of PDF generator (no backend server needed)
"""
from pdf_generator_unicode import generate_hindi_pdf, test_hindi_pdf

print("Testing PDF generator directly...\n")

# Use the built-in test function
test_hindi_pdf()

print("\n✅ Check test_hindi_report.pdf - should have readable Hindi text!")













