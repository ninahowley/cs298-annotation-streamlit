import ast
import os
import sqlite3
import pandas as pd
import streamlit as st

# --- CONFIGURATION ---
DB_NAME = "political_scale_labels.db"
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
    """Reads native Streamlit secrets or local fallback secrets/app_key.txt."""
    if "APP_KEY" in st.secrets:
        return st.secrets["APP_KEY"]

    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()

    return ""


def check_password():
    """Returns True if the user has entered the correct passphrase."""
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


# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS annotations (
            id TEXT PRIMARY KEY,
            account TEXT,
            political_scale TEXT,
            user TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """
    )
    conn.commit()
    conn.close()


def save_user_annotations(user_id, annotations_dict, user_df):
    """Saves all annotations for a student into the SQLite database."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    for item_id, scale_val in annotations_dict.items():
        if scale_val:
            acct_series = user_df.loc[user_df["id"].astype(str) == str(item_id), "account"]
            acct_name = acct_series.values[0] if not acct_series.empty else ""

            cursor.execute(
                """
                INSERT INTO annotations (id, account, political_scale, user)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    political_scale = excluded.political_scale,
                    user = excluded.user,
                    timestamp = CURRENT_TIMESTAMP
            """,
                (str(item_id), str(acct_name), str(scale_val), str(user_id)),
            )

    conn.commit()
    conn.close()


def load_existing_user_annotations(user_id):
    """Loads previously submitted labels for a student from DB to restore progress."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, political_scale FROM annotations WHERE user = ?", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return {row[0]: row[1] for row in rows}


def delete_user_annotations(user_id):
    """Deletes all saved annotations for a student from the database."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM annotations WHERE user = ?", (user_id,))
    conn.commit()
    conn.close()


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
    # 1. Gatekeeper: Require passphrase before loading main app
    if not check_password():
        return

    # 2. Main Page Config
    st.set_page_config(page_title="Political Scale Annotator", layout="wide")
    init_db()

    df = load_data()

    # --- SIDEBAR: USER SELECTION & CLEAR BUTTON ---
    st.sidebar.title("👤 Student Login")
    available_users = sorted(df["user"].dropna().unique().tolist())

    selected_user = st.sidebar.selectbox(
        "Select your User ID:",
        options=["-- Select User --"] + available_users,
    )

    if selected_user == "-- Select User --":
        st.info("👈 Please select your User ID in the sidebar to begin annotating.")
        return

    # Filter dataset for assigned user
    user_df = df[df["user"] == selected_user].reset_index(drop=True)

    if user_df.empty:
        st.warning(f"No profiles assigned to user '{selected_user}'.")
        return

    # Live count of database submissions for selected user
    saved_db_count = len(load_existing_user_annotations(selected_user))
    st.sidebar.info(f"📊 **Submitted to Database:** {saved_db_count} / {len(user_df)} profiles")

    # Clear All Responses Button
    if st.sidebar.button("🗑️ Clear All Responses", use_container_width=True):
        delete_user_annotations(selected_user)
        st.session_state.annotations = {row["id"]: None for _, row in user_df.iterrows()}
        st.session_state.current_idx = 0
        st.sidebar.success("Cleared all responses!")
        st.rerun()

    st.sidebar.divider()
    if st.sidebar.button("🔒 Lock / Logout", use_container_width=True):
        st.session_state.authenticated = False
        st.rerun()

    # --- SESSION STATE INITIALIZATION ---
    if "user_id" not in st.session_state or st.session_state.user_id != selected_user:
        st.session_state.user_id = selected_user
        st.session_state.current_idx = 0
        db_annotations = load_existing_user_annotations(selected_user)
        st.session_state.annotations = {
            row["id"]: db_annotations.get(row["id"], None) for _, row in user_df.iterrows()
        }

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

    # LEFT PANEL: Profile metadata (Username inside, Bio large & dark)
    with col_left:
        with st.container(height=450, key=f"left_container_{current_id}"):
            st.markdown(f"### 📱 Account: @{current_row['account']}")

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
                    font-weight: 600; 
                    line-height: 1.5; 
                    background-color: #f8f9fa; 
                    padding: 14px; 
                    border-left: 5px solid #ff4b4b; 
                    border-radius: 6px; 
                    margin-top: 4px;
                ">
                    {bio_text}
                </div>
                """,
                unsafe_allow_html=True,
            )

    # RIGHT PANEL: Video Captions (dynamic key forces scroll reset on profile change)
    with col_right:
        st.subheader("🎥 Video Posts Captions")
        with st.container(height=450, key=f"video_container_{current_id}"):
            posts_list = current_row["parsed_posts"]
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
    default_index = SCALE_OPTIONS.index(existing_choice) if existing_choice in SCALE_OPTIONS else 3  # Default to 'moderate'

    selected_scale = st.radio(
        "Select the political scale for this profile:",
        options=SCALE_OPTIONS,
        index=default_index,
        horizontal=True,
        key=f"radio_{current_id}",
    )

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
        if st.button("💾 Submit All Annotations to Database", type="primary", use_container_width=True):
            save_user_annotations(selected_user, st.session_state.annotations, user_df)
            st.success(f"✅ All annotations for user '{selected_user}' have been successfully saved to {DB_NAME}!")


if __name__ == "__main__":
    main()