import requests

CIK = "0000320193"  # Apple Inc
USER_AGENT = "A Test Project dev@example.com"

submissions_url = f"https://data.sec.gov/submissions/CIK{CIK}.json"
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
    raise RuntimeError(f"no 10-K found for CIK {CIK}")

cik_no_zeros = str(int(CIK))
accession_no_dashes = accession.replace("-", "")
document_url = f"https://www.sec.gov/Archives/edgar/data/{cik_no_zeros}/{accession_no_dashes}/{document}"

document_response = requests.get(document_url, headers={"User-Agent": USER_AGENT})
document_response.raise_for_status()

output_path = f"{CIK}_{accession}.htm"
with open(output_path, "wb") as f:
    f.write(document_response.content)

print(f"saved {output_path}")