import pandas as pd
from sqlalchemy import create_engine, text
from pathlib import Path

db_path = Path("database/data.db").absolute()
excel_path = Path("input/carga.xlsx").absolute()

engine = create_engine(rf"sqlite:///{db_path}")

with engine.connect() as connection:
    connection.execute(text("DELETE FROM PASE"))
    connection.commit()

df = pd.read_excel(excel_path)
total = df.to_sql("Pase", engine, if_exists="append", index=False)
print(f"{total} registros insertados.")
print(df)
