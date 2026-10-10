"""Download the company master list (symbol, name, sector) from NEPSE.

Output: data/reference/companies.csv

    python ingestion/fetch_companies.py
"""
import pandas as pd
from nepse import Nepse

from common import REFERENCE_DIR


def main():
    nepse = Nepse()
    nepse.setTLSVerification(False)  # nepalstock.com serves an incomplete cert chain
    companies = pd.DataFrame(nepse.getCompanyList())

    out = (companies.rename(columns={
                "companyName": "company_name",
                "sectorName": "sector",
                "instrumentType": "instrument_type"})
           [["symbol", "company_name", "sector", "instrument_type", "status"]]
           .sort_values("symbol"))

    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = REFERENCE_DIR / "companies.csv"
    out.to_csv(path, index=False)
    print(f"Saved {len(out)} companies → {path}")
    print(out["sector"].value_counts().to_string())


if __name__ == "__main__":
    main()
