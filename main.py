import streamlit as st
import pandas as pd
import sqlite3, shutil, os, humanize
from datetime import datetime, date, timedelta
from io import BytesIO
from fpdf import FPDF
import xlsxwriter

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

# Define backup directory
BACKUP_DIR = "backups"
os.makedirs(BACKUP_DIR, exist_ok=True)

# --- Auto Backup & Cleanup ---
def auto_backup_and_cleanup():
    # Generate timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    backup_filename = f"trip_data_backup_{timestamp}.db"
    backup_path = os.path.join(BACKUP_DIR, backup_filename)

    # Create backup if one for today doesn't already exist
    today_str = datetime.now().strftime("%Y-%m-%d")
    existing_today = any(today_str in fname for fname in os.listdir(BACKUP_DIR))

    if not existing_today:
        shutil.copy(DB_FILE, backup_path)

    # Cleanup: Delete backups older than 3 days
    cutoff_time = datetime.now() - timedelta(days=3)
    for file in os.listdir(BACKUP_DIR):
        full_path = os.path.join(BACKUP_DIR, file)
        if os.path.isfile(full_path):
            modified_time = datetime.fromtimestamp(os.path.getmtime(full_path))
            if modified_time < cutoff_time:
                os.remove(full_path)

# Call the function at app start
auto_backup_and_cleanup()

st.title("🚗 Vehicle Trip Sheet Tracking")

# Admin Access Tab
tab1, tab2 = st.tabs(["Trip Entry", "🔒 Admin Panel"])

logout_button_clicked = False

with tab2:
    if "admin_logged_in" not in st.session_state:
        st.session_state.admin_logged_in = False

    if not st.session_state.admin_logged_in:
        admin_password = st.text_input("Enter Admin Password", type="password")
        if st.button("Login"):
            if admin_password == "RVPL@123":  # Change password securely in deployment
                st.session_state.admin_logged_in = True
                st.success("Logged in successfully.")
            else:
                st.error("Incorrect password.")
    else:
        st.success("Admin Logged In")
        if st.button("Logout"):
            st.session_state.admin_logged_in = False
            logout_button_clicked = True
            st.rerun()

with tab1:
    vehicle_no = st.selectbox("Select Vehicle", VEHICLE_LIST)
    trip_date = st.date_input("Trip Date", date.today())
    remark = st.text_input("Remark (e.g., Sunday, Holiday, etc.)")

    query = "SELECT * FROM trips WHERE vehicle=? AND trip_date=? ORDER BY id DESC"
    vehicle_data = pd.read_sql(query, conn, params=(vehicle_no, str(trip_date)))

    if not vehicle_data.empty:
        st.subheader("Last Entry")
        last_row = vehicle_data.iloc[[-1]].copy()
        last_row["datetime"] = last_row["trip_date"]
        last_row.columns = ["ID", "Date", "Vehicle No", "Trip Date", "Start KM", "End KM", "KM Travelled", "Remark"]
        st.dataframe(last_row[["Date", "Vehicle No", "Start KM", "End KM", "KM Travelled"]])
    else:
        st.info("No entries yet for this vehicle on selected date.")

    total_km = pd.read_sql("SELECT SUM(km_travelled) as total FROM trips WHERE vehicle=?", conn, params=(vehicle_no,)).iloc[0]['total'] or 0
    st.metric("Total KM Travelled", f"{total_km} km")

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
if st.session_state.get("admin_logged_in"):
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
    
    # --- Backup: Download current DB file ---
    # Ensure backup directory exists
    st.subheader("🧾 Database Backup & Versioned Restore")

    # 1. Create timestamped backup
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    backup_filename = f"trip_data_backup_{timestamp}.db"
    backup_path = os.path.join(BACKUP_DIR, backup_filename)

    if st.button("📁 Create Timestamped Backup"):
        shutil.copy(DB_FILE, backup_path)
        st.success(f"✅ Backup saved as {backup_filename}")

    # 2. List all available backups for download or restore
    backup_files = sorted(os.listdir(BACKUP_DIR), reverse=True)
    if backup_files:
        selected_backup = st.selectbox("📜 Available Backups", backup_files)

        # Download selected backup
        with open(os.path.join(BACKUP_DIR, selected_backup), "rb") as f:
            st.download_button(
                label="⬇️ Download Selected Backup",
                data=f,
                file_name=selected_backup,
                mime="application/octet-stream",
                key=f"download_{selected_backup}"  # unique key
            )

        # Restore selected backup
        if st.button("♻️ Restore Selected Backup"):
            shutil.copy(os.path.join(BACKUP_DIR, selected_backup), DB_FILE)
            st.success("✅ Restored from selected backup.")
            st.rerun()
    else:
        st.info("No backups found yet.")

    # 3. Restore from uploaded file
    st.divider()
    uploaded_db = st.file_uploader("📤 Upload a new .db file to restore", type=["db"])
    if uploaded_db is not None:
        try:
            uploaded_filename = f"uploaded_restore_{timestamp}.db"
            uploaded_path = os.path.join(BACKUP_DIR, uploaded_filename)

            # Save uploaded file to backups folder
            with open(uploaded_path, "wb") as f:
                f.write(uploaded_db.read())

            # Backup current DB before replacing
            shutil.copy(DB_FILE, f"{DB_FILE}.bak")

            # Replace main DB
            shutil.copy(uploaded_path, DB_FILE)
            st.success(f"✅ Uploaded DB restored. Backup also saved as {uploaded_filename}")
            st.rerun()

        except Exception as e:
            st.error(f"❌ Failed to restore database: {e}")

    # backup log viewer
    st.subheader("📜 Backup Log Viewer")

    # List and display backup files
    backup_entries = []
    for file in sorted(os.listdir(BACKUP_DIR), reverse=True):
        path = os.path.join(BACKUP_DIR, file)
        if os.path.isfile(path) and file.endswith(".db"):
            created_at = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M")
            size_kb = os.path.getsize(path) / 1024
            backup_entries.append({
                "Backup File": file,
                "Date Created": created_at,
                "Size (KB)": f"{size_kb:.1f}"
            })

    if backup_entries:
        df_log = pd.DataFrame(backup_entries)
        st.dataframe(df_log)

        # Optional: Select and download from the list
        selected_file = st.selectbox("Download a backup", df_log["Backup File"], key="backup_file_select")
        with open(os.path.join(BACKUP_DIR, selected_file), "rb") as f:
            st.download_button(
                label="⬇️ Download Selected Backup",
                data=f,
                file_name=selected_file,
                mime="application/octet-stream",
                key=f"download_button_{selected_file}"  # Unique key for each file
            )
    else:
        st.info("No backup files available.")

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

        for col in ["Sr. No", "Start KM", "End KM", "KM Travelled"]:
            df_download[col] = pd.to_numeric(df_download[col], errors="coerce").fillna(0).astype(int)

        st.dataframe(df_download)

        csv = df_download.to_csv(index=False).encode("utf-8")
        st.download_button("Download CSV", csv, f"{vehicle_no}_trip_data.csv", "text/csv")

        # Excel generation
        excel_buffer = BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
            df_download.to_excel(writer, index=False, sheet_name="Trips")

        st.download_button("Download Excel", data=excel_buffer.getvalue(), file_name=f"{vehicle_no}_trip_data.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        # PDF generation with table formatting and signature column
        pdf = FPDF(orientation='L', unit='mm', format='A4')
        pdf.add_page()
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 10, f"Trip Report for {vehicle_no}", ln=True, align='C')
        pdf.ln(5)

        col_widths = [10, 25, 35, 30, 30, 30, 65, 35]
        headers = list(df_download.columns) + ["Signature"]

        pdf.set_font("Arial", "B", 10)
        for i, header in enumerate(headers):
            pdf.cell(col_widths[i], 10, header, border=1)
        pdf.ln()

        pdf.set_font("Arial", size=10)
        for index, row in df_download.iterrows():
            for i, value in enumerate(row):
                pdf.cell(col_widths[i], 10, str(value), border=1)
            pdf.cell(col_widths[-1], 10, "", border=1)  # Signature column
            pdf.ln()

        pdf_bytes = BytesIO()
        pdf_output = pdf.output(dest='S').encode('latin1')
        pdf_bytes.write(pdf_output)
        pdf_bytes.seek(0)

        st.download_button("Download PDF", data=pdf_bytes, file_name=f"{vehicle_no}_trip_data.pdf", mime="application/pdf")
    else:
        st.warning("No data found for the selected range.")