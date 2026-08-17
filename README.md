# Vietnam Monetary & Banking Liquidity Intelligence V6

## Main V6 upgrade
V6 adds a bank-by-bank transmission layer:
System liquidity stress -> funding vulnerability -> funding cost shock -> stressed NIM -> GREEN/AMBER/RED watch flag.

## Real-data-first workflow
```bash
pip install -r requirements.txt
python update_macro.py
python bank_data.py
python bank_stress.py
streamlit run app.py
```

`bank_data.py` uses Vnstock Fundamental for quarterly bank balance sheets, income statements and financial ratios. It attempts to map actual bank metrics such as customer loans, deposits, interbank borrowing, CASA and NIM. If an item cannot be mapped, it stays blank.

## Bank universe
VCB, BID, CTG, TCB, MBB, ACB, HDB, VPB, STB, VIB, SHB, TPB, LPB, OCB, MSB, SSB, EIB, NAB, KLB, BAB.

Edit `config/banks.json` to change the universe.

## Production safeguards
- No synthetic fill for bank financial statements.
- Vulnerability output gated at >=50% metric coverage.
- ACTUAL / CALC / ESTIMATE / ASSUMPTION lineage kept separate.
- Stress coefficients are assumptions and are editable in Excel/Streamlit.
