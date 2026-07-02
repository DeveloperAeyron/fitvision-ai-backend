import streamlit as st
import requests
import os

st.set_page_config(page_title="FitVision Testing Panel", page_icon="💪", layout="centered")
st.title("💪 FitVision Testing Interface")

API_URL = "http://127.0.0.1:8000"

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "username" not in st.session_state:
    st.session_state.username = ""

if not st.session_state.logged_in:
    tab1, tab2 = st.tabs(["🔒 Login", "📝 Sign Up"])
    
    with tab1:
        st.subheader("Login into Session Profile")
        lin_user = st.text_input("Username", key="login_user")
        lin_pass = st.text_input("Password", type="password", key="login_pass")
        if st.button("Authenticate"):
            res = requests.post(f"{API_URL}/login", data={"username": lin_user, "password": lin_pass})
            if res.status_code == 200:
                st.session_state.logged_in = True
                st.session_state.username = lin_user
                st.success("Welcome back!")
                st.rerun()
            else:
                st.error("Invalid username or password configuration.")

    with tab2:
        st.subheader("Create a New Account")
        sup_user = st.text_input("Choose Username", key="signup_user")
        sup_pass = st.text_input("Choose Password", type="password", key="signup_pass")
        if st.button("Register Account"):
            res = requests.post(f"{API_URL}/signup", data={"username": sup_user, "password": sup_pass})
            if res.status_code == 200:
                st.success("Registration success! You can switch to login now.")
            else:
                st.error("Username already taken or invalid parameters.")

else:
    st.sidebar.write(f"Active User: **{st.session_state.username}**")
    if st.sidebar.button("Log Out"):
        st.session_state.logged_in = False
        st.rerun()

    st.subheader("🚀 Step 2: Test Pose Estimation")
    uploaded_video = st.file_uploader("Upload a gym video clip (.mp4)", type=["mp4", "mov", "avi"])

    if uploaded_video is not None:
        st.info("Uploading video payload to backend processing core...")
        
        files = {"file": (uploaded_video.name, uploaded_video.getvalue(), uploaded_video.type)}
        response = requests.post(f"{API_URL}/detection", files=files)
        
        if response.status_code == 200:
            st.success("Video processed completely from server node!")
            
            saved_output_path = f"processed_preview_{uploaded_video.name}"
            with open(saved_output_path, "wb") as f:
                f.write(response.content)
                
            st.subheader("📊 Output Stream Result:")
            st.video(saved_output_path)
        else:
            st.error("Error communicating with the FastAPI parsing loop.")