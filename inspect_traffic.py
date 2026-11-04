import pandas as pd

f = "./data/raw/traffic/trafic_2025.xlsx"

with pd.ExcelFile(f) as x:
    print("========================================")
    print("TRAFFIC DATA LUXEMBOURG")
    print("========================================")
    print("\nSHEETS:")
    print(x.sheet_names)

    for s in x.sheet_names:
        df = pd.read_excel(x, sheet_name=s, nrows=5)

        print("\n========================================")
        print("SHEET:", s)
        print("========================================")
        print("NUMBER OF COLUMNS:", len(df.columns))
        print("COLUMNS:")
        for i, col in enumerate(df.columns, 1):
            print(f"  {i}. {col}")

        print("\n5 FIRST ROWS:")
        print(df.to_string(index=False))
