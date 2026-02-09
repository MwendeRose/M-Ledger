import re

def parse_transactions(text):
    txs = []
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    i = 0

    while i < len(lines):
        line = lines[i]

        m = re.search(r'([A-Z0-9]+)\s+(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})', line)
        if not m:
            i += 1
            continue

        ref = m.group(1)
        date = m.group(2)
        time = m.group(3)

        desc_parts = [line[m.end():].strip()]

        i += 1
        while i < len(lines) and not lines[i].startswith("Completed"):
            desc_parts.append(lines[i])
            i += 1

        if i >= len(lines):
            break

        nums = re.findall(r'-?[\d,]+\.\d+', lines[i])
        if len(nums) >= 2:
            amount = float(nums[0].replace(",", ""))
            balance = float(nums[1].replace(",", ""))
        else:
            i += 1
            continue

        desc = " ".join(desc_parts)

        if "charge" in desc.lower():
            cat = "charge"
        elif amount > 0:
            cat = "income"
        else:
            cat = "expense"

        txs.append({
            "ref": ref,
            "date": date,
            "time": time,
            "details": desc,
            "amount": abs(amount),
            "balance": balance,
            "category": cat
        })

        i += 1

    return txs
