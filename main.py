import os

import requests

USER_AGENT = "A Test Project dev@example.com"

COMPANIES = [
    ("Apple Inc", "0000320193"),
    ("Microsoft Corp", "0000789019"),
    ("Amazon.com Inc", "0001018724"),
]

for name, cik in COMPANIES:
    submissions_url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    response = requests.get(submissions_url, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    recent = response.json()["filings"]["recent"]

    accession = None
    document = None
    for form, acc, doc in zip(recent["form"], recent["accessionNumber"], recent["primaryDocument"]):
        if form == "10-K":
            accession = acc
            document = doc
            break

    if accession is None:
        print(f"no 10-K found for {name}, skipping")
        continue

    output_path = f"{cik}_{accession}.htm"

    if os.path.exists(output_path):
        print(f"already have {name} ({output_path}), skipping")
        continue

    cik_no_zeros = str(int(cik))
    accession_no_dashes = accession.replace("-", "")
    document_url = f"https://www.sec.gov/Archives/edgar/data/{cik_no_zeros}/{accession_no_dashes}/{document}"

    document_response = requests.get(document_url, headers={"User-Agent": USER_AGENT})
    document_response.raise_for_status()

    with open(output_path, "wb") as f:
        f.write(document_response.content)

    print(f"saved {name} -> {output_path}")