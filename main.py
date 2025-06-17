import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, date
from io import BytesIO
from fpdf import FPDF

# Database setup
DB_FILE = "trip_data.db"
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
cursor = conn.cursor()

# Ensure 'remark' column exists in trips table
cursor.execute('''
    CREATE TABLE IF NOT EXISTS trips (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        datetime TEXT,
        vehicle TEXT,
        trip_date TEXT,
        start_km INTEGER,
        end_km INTEGER,
        km_travelled INTEGER
    )
''')
try:
    cursor.execute("ALTER TABLE trips ADD COLUMN remark TEXT")
    conn.commit()
except sqlite3.OperationalError:
    pass  # Column already exists

VEHICLE_LIST = ["CA Gaadi", "Manish", "Ertiga", "XL6"]

st.title("🚗 Vehicle Trip Sheet Tracking")

vehicle_no = st.selectbox("Select Vehicle", VEHICLE_LIST)
trip_date = st.date_input("Trip Date", date.today())
remark = st.text_input("Remark (e.g., Sunday, Holiday, etc.)")

# Load data for vehicle and date
query = "SELECT * FROM trips WHERE vehicle=? AND trip_date=? ORDER BY id DESC"
vehicle_data = pd.read_sql(query, conn, params=(vehicle_no, str(trip_date)))

# Display last entry
if not vehicle_data.empty:
    st.subheader("Last Entry")
    last_row = vehicle_data.iloc[[-1]].copy()
    last_row["datetime"] = last_row["trip_date"]
    last_row.columns = ["ID", "Date", "Vehicle No", "Trip Date", "Start KM", "End KM", "KM Travelled", "Remark"]
    st.dataframe(last_row[["Date", "Vehicle No", "Start KM", "End KM", "KM Travelled"]])
else:
    st.info("No entries yet for this vehicle on selected date.")

# Display total km
total_km = pd.read_sql("SELECT SUM(km_travelled) as total FROM trips WHERE vehicle=?", conn, params=(vehicle_no,)).iloc[0]['total'] or 0
st.metric("Total KM Travelled", f"{total_km} km")

# Entry logic
existing_start = not vehicle_data.empty and vehicle_data.iloc[-1]['start_km'] is not None
existing_end = not vehicle_data.empty and vehicle_data.iloc[-1]['end_km'] is not None

st.subheader("Add Trip Entry")

if existing_start and existing_end:
    st.warning("Trip data for this date is already fully recorded.")
elif not existing_start:
    start_km = st.number_input("Enter Start KM", min_value=0, step=1)
    if st.button("Submit Start KM"):
        dt_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            INSERT INTO trips (datetime, vehicle, trip_date, start_km, end_km, km_travelled, remark)
            VALUES (?, ?, ?, ?, NULL, NULL, ?)
        """, (dt_now, vehicle_no, str(trip_date), int(start_km), remark))
        conn.commit()
        st.success("Start KM recorded.")
        st.rerun()
elif existing_start and not existing_end:
    start_km_value = vehicle_data.iloc[-1]['start_km']
    st.text(f"Start KM: {start_km_value}")
    end_km = st.number_input("Enter End KM", min_value=int(start_km_value) + 1, step=1)
    if st.button("Submit End KM"):
        km_travelled = int(end_km) - int(start_km_value)
        row_id = vehicle_data.iloc[-1]['id']
        cursor.execute("""
            UPDATE trips SET end_km=?, km_travelled=? WHERE id=?
        """, (int(end_km), km_travelled, int(row_id)))
        conn.commit()
        st.success("End KM recorded.")
        st.rerun()

# Download section
st.subheader("Download Trip Data")
start_date = st.date_input("Start Date", date.today().replace(day=1))
end_date = st.date_input("End Date", date.today())

query = """
    SELECT trip_date AS "Date", datetime AS "Start Time", start_km AS "Start KM",
           end_km AS "End KM", km_travelled AS "KM Travelled", remark AS "Remarks"
    FROM trips
    WHERE vehicle=? AND date(trip_date) BETWEEN ? AND ?
"""
df_download = pd.read_sql(query, conn, params=(vehicle_no, str(start_date), str(end_date)))
df_download.insert(0, "Sr. No", range(1, len(df_download) + 1))
df_download.insert(1, "Vehicle Name", vehicle_no)
df_download["End Time"] = df_download["Start Time"]
df_download["Signature"] = ""
df_download = df_download[["Sr. No", "Date", "Vehicle Name", "Start Time", "Start KM", "End Time", "End KM", "KM Travelled", "Remarks", "Signature"]]

# Add total row
total_row = pd.DataFrame({
    "Sr. No": [""],
    "Date": [""],
    "Vehicle Name": ["Total"],
    "Start Time": [""],
    "Start KM": [""],
    "End Time": [""],
    "End KM": [""],
    "KM Travelled": [df_download["KM Travelled"].sum()],
    "Remarks": [""],
    "Signature": [""]
})
df_final = pd.concat([df_download, total_row], ignore_index=True)

st.dataframe(df_final)

# CSV Download
csv_data = df_final.to_csv(index=False).encode('utf-8')
st.download_button("📄 Download CSV", csv_data, f"{vehicle_no}_trip_summary.csv", "text/csv")

# Excel Download
output = BytesIO()
with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
    df_final.to_excel(writer, index=False, sheet_name='Trips')
excel_data = output.getvalue()
st.download_button("📈 Download Excel (.xlsx)", excel_data, f"{vehicle_no}_trip_summary.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# PDF Download
class PDF(FPDF):
    def header(self):
        self.set_font("Arial", "B", 12)
        self.cell(0, 10, f"{vehicle_no} Trip Summary", ln=True, align='C')
        self.set_font("Arial", "", 10)
        self.cell(0, 10, f"Period: {start_date} to {end_date}", ln=True, align='C')
        self.ln(5)

    def table(self, data):
        self.set_font("Arial", "B", 9)
        headers = ["Sr. No", "Date", "Vehicle Name", "Start Time", "Start KM", "End Time", "End KM", "KM Travelled", "Remarks", "Signature"]
        col_widths = [10, 20, 25, 25, 20, 25, 20, 25, 25, 25]

        for i, header in enumerate(headers):
            self.cell(col_widths[i], 10, header, border=1)
        self.ln()

        self.set_font("Arial", "", 8)
        for _, row in data.iterrows():
            self.cell(col_widths[0], 10, str(row["Sr. No"]), border=1)
            self.cell(col_widths[1], 10, str(row["Date"]), border=1)
            self.cell(col_widths[2], 10, str(row["Vehicle Name"]), border=1)
            self.cell(col_widths[3], 10, str(row["Start Time"]), border=1)
            self.cell(col_widths[4], 10, str(row["Start KM"]), border=1)
            self.cell(col_widths[5], 10, str(row["End Time"]), border=1)
            self.cell(col_widths[6], 10, str(row["End KM"]), border=1)
            self.cell(col_widths[7], 10, str(row["KM Travelled"]), border=1)
            self.cell(col_widths[8], 10, str(row["Remarks"]), border=1)
            self.cell(col_widths[9], 10, str(row["Signature"]), border=1)
            self.ln()

pdf = PDF()
pdf.add_page()
pdf.table(df_final)
pdf_bytes = pdf.output(dest='S').encode('latin1')
st.download_button("📄 Download PDF", pdf_bytes, f"{vehicle_no}_trip_summary.pdf", "application/pdf")