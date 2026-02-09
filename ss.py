from pdf_parser import extract_text

text = extract_text("MPESA_Statement_2025-04-30_to_2025-04-01_2547xxxxxx963.pdf")
print(text[:2000])  # print first 2000 characters
print("\n--- Total characters extracted:", len(text))
