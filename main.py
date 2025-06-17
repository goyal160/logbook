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
        km_travelled INTEGER,
        remark TEXT
    )
''')

VEHICLE_LIST = ["CA Gaadi", "Manish", "Ertiga", "XL6"]

st.title("🚗 Vehicle Trip Sheet Tracking")

# Admin Access
admin_password = st.sidebar.text_input("Enter Admin Password", type="password")
is_admin = (admin_password == "RVPL@123")  # Change password securely in deployment

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

# Admin Editing Option
if is_admin:
    st.subheader("🛠 Admin: Edit/Delete Entry")
    all_data = pd.read_sql("SELECT * FROM trips ORDER BY trip_date DESC", conn)
    st.dataframe(all_data)

    edit_id = st.number_input("Enter ID to Edit/Delete", min_value=1, step=1)
    action = st.radio("Action", ["Update", "Delete"])

    if action == "Update":
        new_start = st.number_input("New Start KM", min_value=0, step=1)
        new_end = st.number_input("New End KM", min_value=0, step=1)
        new_remark = st.text_input("New Remark")
        if st.button("Update Entry"):
            new_km = new_end - new_start
            cursor.execute("UPDATE trips SET start_km=?, end_km=?, km_travelled=?, remark=? WHERE id=?",
                           (new_start, new_end, new_km, new_remark, edit_id))
            conn.commit()
            st.success("Entry updated.")
            st.rerun()

    if action == "Delete":
        if st.button("Delete Entry"):
            cursor.execute("DELETE FROM trips WHERE id=?", (edit_id,))
            conn.commit()
            st.success("Entry deleted.")
            st.rerun()

    if st.button("📃 Backup Data to CSV"):
        backup_df = pd.read_sql("SELECT * FROM trips", conn)
        csv_bytes = backup_df.to_csv(index=False).encode('utf-8')
        st.download_button("⬇️ Download Backup CSV", csv_bytes, "trip_backup.csv", "text/csv")

    # Admin Graph: Daily KM by Vehicle
    st.subheader("📊 Daily KM by Vehicle")
    graph_start = st.date_input("Graph Start Date", date.today().replace(day=1))
    graph_end = st.date_input("Graph End Date", date.today())

    km_data = pd.read_sql("""
        SELECT trip_date, vehicle, SUM(km_travelled) as total_km
        FROM trips
        WHERE date(trip_date) BETWEEN ? AND ?
        GROUP BY trip_date, vehicle
        ORDER BY trip_date ASC
    """, conn, params=(str(graph_start), str(graph_end)))

    if not km_data.empty:
        km_pivot = km_data.pivot(index='trip_date', columns='vehicle', values='total_km').fillna(0)
        st.line_chart(km_pivot)
    else:
        st.info("No data available for selected date range.")

# Download Trip Data Section
st.subheader("⬇️ Download Trip Data")
download_start = st.date_input("Start Date", date.today().replace(day=1), key="dl_start")
download_end = st.date_input("End Date", date.today(), key="dl_end")

if st.button("⬇️ Download Trip Data"):
    query = """
        SELECT trip_date AS "Date", datetime AS "Start Time", 
               start_km AS "Start KM", end_km AS "End KM", 
               km_travelled AS "KM Travelled", remark AS "Remarks" 
        FROM trips 
        WHERE vehicle=? AND date(trip_date) BETWEEN ? AND ?
    """
    df_download = pd.read_sql(query, conn, params=(vehicle_no, str(download_start), str(download_end)))

    if not df_download.empty:
        df_download.insert(0, "Sr. No", range(1, len(df_download) + 1))

        # Convert columns to appropriate types to avoid Arrow error
        df_download["Sr. No"] = pd.to_numeric(df_download["Sr. No"], errors="coerce").fillna(0).astype(int)
        df_download["Start KM"] = pd.to_numeric(df_download["Start KM"], errors="coerce").fillna(0).astype(int)
        df_download["End KM"] = pd.to_numeric(df_download["End KM"], errors="coerce").fillna(0).astype(int)
        df_download["KM Travelled"] = pd.to_numeric(df_download["KM Travelled"], errors="coerce").fillna(0).astype(int)

        st.dataframe(df_download)

        csv = df_download.to_csv(index=False).encode("utf-8")
        st.download_button("Download CSV", csv, f"{vehicle_no}_trip_data.csv", "text/csv")
    else:
        st.warning("No data found for the selected range.")