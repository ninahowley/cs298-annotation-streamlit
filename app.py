import ast
import os
from datetime import datetime
import pandas as pd
import streamlit as st
from streamlit_gsheets import GSheetsConnection

# --- CONFIGURATION ---
CSV_FILE = "data_cleaned.csv"
KEY_FILE = os.path.join("secrets", "app_key.txt")

SCALE_OPTIONS = [
    "extremely liberal",
    "liberal",
    "slightly liberal",
    "moderate",
    "slightly conservative",
    "conservative",
    "extremely conservative",
]


# --- PASSPHRASE AUTHENTICATION ---
def get_stored_app_key():
    if "APP_KEY" in st.secrets:
        return st.secrets["APP_KEY"]

    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()

    return ""


def check_password():
    if st.session_state.get("authenticated", False):
        return True

    st.set_page_config(page_title="Access Gate", layout="centered")

    st.title("🔒 Restricted Access")
    st.write("Please enter the passphrase to access the Political Scale Annotator.")

    correct_key = get_stored_app_key()
    user_input = st.text_input("Passphrase:", type="password", key="passphrase_input")

    if st.button("Enter Website", type="primary", use_container_width=True):
        if user_input == correct_key:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("❌ Incorrect passphrase. Please try again.")

    return False


# --- GOOGLE SHEETS DATABASE OPERATIONS ---
def get_gsheets_connection():
    return st.connection("gsheets", type=GSheetsConnection)


def fetch_all_annotations():
    """Reads live annotations from Google Sheets with 60s cache."""
    conn = get_gsheets_connection()
    try:
        df_sheet = conn.read(ttl=60)
        if df_sheet is None or df_sheet.empty:
            return pd.DataFrame(columns=["id", "account", "political_scale", "user", "timestamp"])
        df_sheet["id"] = df_sheet["id"].astype(str)
        df_sheet["user"] = df_sheet["user"].astype(str)
        return df_sheet
    except Exception:
        return pd.DataFrame(columns=["id", "account", "political_scale", "user", "timestamp"])


def load_existing_user_annotations(user_id):
    """Loads a specific user's saved annotations from Google Sheets."""
    df_sheet = fetch_all_annotations()
    if df_sheet.empty:
        return {}
    user_rows = df_sheet[df_sheet["user"] == str(user_id)]
    return dict(zip(user_rows["id"], user_rows["political_scale"]))


def save_user_annotations(user_id, annotations_dict, user_df):
    """Upserts user annotations to Google Sheets."""
    conn = get_gsheets_connection()
    df_sheet = fetch_all_annotations()

    if not df_sheet.empty:
        df_sheet = df_sheet[df_sheet["user"] != str(user_id)]

    new_rows = []
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for item_id, scale_val in annotations_dict.items():
        if scale_val:
            acct_series = user_df.loc[user_df["id"].astype(str) == str(item_id), "account"]
            acct_name = acct_series.values[0] if not acct_series.empty else ""

            new_rows.append(
                {
                    "id": str(item_id),
                    "account": str(acct_name),
                    "political_scale": str(scale_val),
                    "user": str(user_id),
                    "timestamp": timestamp,
                }
            )

    if new_rows:
        df_new = pd.DataFrame(new_rows)
        df_updated = pd.concat([df_sheet, df_new], ignore_index=True)
    else:
        df_updated = df_sheet

    conn.update(data=df_updated)
    st.cache_data.clear()


def delete_user_annotations(user_id):
    """Deletes all saved annotations for a specific student from Google Sheets."""
    conn = get_gsheets_connection()
    df_sheet = fetch_all_annotations()

    if not df_sheet.empty:
        df_updated = df_sheet[df_sheet["user"] != str(user_id)]
        conn.update(data=df_updated)
        st.cache_data.clear()


# --- DATA LOADING ---
@st.cache_data
def load_data():
    df = pd.read_csv(CSV_FILE)

    df["id"] = df["id"].astype(str)
    df["user"] = df["user"].astype(str).str.strip()

    def parse_posts(val):
        if pd.isna(val) or not val:
            return []
        try:
            return ast.literal_eval(val)
        except Exception:
            return []

    df["parsed_posts"] = df["posts"].apply(parse_posts)
    return df


# --- MAIN APP UI ---
def main():
    if not check_password():
        return

    st.set_page_config(page_title="Political Scale Annotator", layout="wide")

    df = load_data()

    # --- SIDEBAR: USER SELECTION ---
    st.sidebar.title("👤 Student Login")
    available_users = sorted(df["user"].dropna().unique().tolist())

    selected_user = st.sidebar.selectbox(
        "Select your User ID:",
        options=["-- Select User --"] + available_users,
    )

    if selected_user == "-- Select User --":
        st.info("👈 Please select your User ID in the sidebar to begin annotating.")
        return

    user_df = df[df["user"] == selected_user].reset_index(drop=True)

    if user_df.empty:
        st.warning(f"No profiles assigned to user '{selected_user}'.")
        return

    # --- SESSION STATE INITIALIZATION (Runs ONCE per user login) ---
    if "user_id" not in st.session_state or st.session_state.user_id != selected_user:
        st.session_state.user_id = selected_user
        st.session_state.current_idx = 0

        saved_annotations = load_existing_user_annotations(selected_user)
        st.session_state.annotations = {
            row["id"]: saved_annotations.get(row["id"], None) for _, row in user_df.iterrows()
        }
        # Track submitted count strictly from Google Sheets state
        st.session_state.db_submitted_count = len(saved_annotations)

    # Sidebar counter reads strictly from submitted state (does not change on radio clicks)
    submitted_count = st.session_state.get("db_submitted_count", 0)
    st.sidebar.info(f"📊 **Submitted to Database:** {submitted_count} / {len(user_df)} profiles")

    # Clear All Responses Button
    if st.sidebar.button("🗑️ Clear All Responses", use_container_width=True):
        delete_user_annotations(selected_user)
        st.session_state.annotations = {row["id"]: None for _, row in user_df.iterrows()}
        st.session_state.db_submitted_count = 0
        st.session_state.current_idx = 0
        st.sidebar.success("Cleared all responses from Google Sheets!")
        st.rerun()

    st.sidebar.divider()
    if st.sidebar.button("🔒 Lock / Logout", use_container_width=True):
        st.session_state.authenticated = False
        st.rerun()

    idx = st.session_state.current_idx
    current_row = user_df.iloc[idx]
    current_id = current_row["id"]

    # --- TOP PROGRESS BAR & HEADER ---
    st.title("🏷️ Political Scale Profile Annotator")

    progress = (idx + 1) / len(user_df)
    st.progress(progress)
    st.caption(
        f"Assigned User: **{selected_user}** | Profile **{idx + 1}** of **{len(user_df)}**"
    )

    # --- PROFILE DISPLAY ---
    col_left, col_right = st.columns([1, 1], gap="medium")

    # LEFT PANEL: Profile metadata
    with col_left:
        with st.container(height=450, key=f"left_container_{current_id}"):
            st.subheader(f"Account: @{current_row['account']}")
            st.page_link(current_row["profile_link"], label="Account link")

            m1, m2, m3 = st.columns(3)
            m1.metric("Followers", f"{current_row['followers']:,}" if pd.notna(current_row['followers']) else "N/A")
            m2.metric("Verified", "✅ Yes" if current_row.get("is_verified") else "❌ No")
            m3.metric("Category", str(current_row.get("account_category", "N/A")))

            st.markdown(f"**Full Name:** {current_row['full_name']}")
            st.markdown("**Biography:**")

            bio_text = current_row['biography'] if pd.notna(current_row['biography']) else "No biography available."
            st.markdown(
                f"""
                <div style="
                    font-size: 1.25rem; 
                    color: #111111; 
                    line-height: 1.5; 
                    background-color: #f8f9fa; 
                    padding: 14px; 
                    margin-top: 4px;
                ">
                    {bio_text}
                </div>
                """,
                unsafe_allow_html=True,
            )

    # RIGHT PANEL: Video Captions
    with col_right:
        st.subheader("Video Posts Captions")
        with st.container(height=450, key=f"video_container_{current_id}"):
            posts_list = current_row["parsed_posts"]
            if posts_list:
                posts_list = sorted(posts_list, key=lambda x: str(x.get("datetime", "")), reverse=True)
            if posts_list:
                for i, post in enumerate(posts_list, 1):
                    caption = post.get("caption", "No caption provided.")
                    content_type = post.get("content_type", "Video")
                    dt = post.get("datetime", "")[:10]

                    st.markdown(f"**Video #{i}** *({content_type} • {dt})*")
                    st.write(f"💬 {caption}")
                    st.divider()
            else:
                st.write("No video posts found for this profile.")

    # --- ANNOTATION SELECTION AREA ---
    st.markdown("---")
    st.subheader("⚖️ Annotate Political Scale")

    existing_choice = st.session_state.annotations.get(current_id)
    default_index = SCALE_OPTIONS.index(existing_choice) if existing_choice in SCALE_OPTIONS else 3

    selected_scale = st.radio(
        "Select the political scale for this profile:",
        options=SCALE_OPTIONS,
        index=default_index,
        horizontal=True,
        key=f"radio_{current_id}",
    )

    # Store locally in session state (does NOT trigger Google Sheets API or update sidebar count)
    st.session_state.annotations[current_id] = selected_scale

    # --- NAVIGATION & SUBMIT BUTTONS ---
    nav_col1, nav_col2, nav_col3 = st.columns([2, 4, 2])

    with nav_col1:
        if st.button("⬅️ Previous", disabled=(idx == 0), use_container_width=True):
            st.session_state.current_idx -= 1
            st.rerun()

    with nav_col3:
        if idx < len(user_df) - 1:
            if st.button("Next ➡️", use_container_width=True):
                st.session_state.current_idx += 1
                st.rerun()

    with nav_col2:
        if st.button("💾 Submit All Annotations to Google Sheets", type="primary", use_container_width=True):
            save_user_annotations(selected_user, st.session_state.annotations, user_df)

            # Update submitted count in session state only on explicit submit
            new_count = sum(1 for v in st.session_state.annotations.values() if v is not None)
            st.session_state.db_submitted_count = new_count

            st.success(f"✅ All annotations for user '{selected_user}' have been saved directly to Google Sheets!")
            st.rerun()


if __name__ == "__main__":
    main()