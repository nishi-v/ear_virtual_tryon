import numpy as np
import cv2
import streamlit as st
import requests
from PIL import Image
import json
from typing import List, Dict
import time
from dotenv import load_dotenv
import os
from pathlib import Path

# Get the current working directory
dir = Path(os.getcwd())

# Load environment variables from .env file
ENV_PATH = dir / '.env'
load_dotenv(ENV_PATH)

# Get API URL from environment variables
API_URL = os.environ["API_URL"]
BEARER_TOKEN = os.environ["BEARER_TOKEN"]

st.title('Earring Virtual Try On')

# Initialize session state if not already done
if "earring_selected" not in st.session_state:
    st.session_state.earring_selected = False

earrings = {
    "Earring 1": "earrings/EFBS013P1F.png",
    "Earring 2": "earrings/EFBS017D1F.png",
    "Earring 3": "earrings/EFBS020S1F.png",
    "Earring 4": "earrings/EFBS023P1F.png",
    "Earring 5": "earrings/EFGV024D1F.png"
}

if not st.session_state.earring_selected:
    # Display earring images with "Try On" buttons
    for name, image_path in earrings.items():
        obj = Image.open(image_path).convert("RGBA")
        st.image(obj, caption=name, width=100)
        
        if st.button(f"Try On {name}"):
            st.session_state.earring_selected = True
            st.session_state.selected_earring = name
            st.session_state.object = obj
            break  # Exit the loop after an earring is selected

else:
    # Capture Ear Image and Overlay Selected Earring
    obj = st.session_state.object
    
    # Display selected earring
    st.image(obj, caption="Selected Earring", width=100)

    # Provide options to either upload or capture an image
    option = st.radio("Choose Image Source", ("Capture Image", "Upload Image"))

    if option == "Capture Image":
        # Streamlit widget to capture an image using the webcam
        camera_image = st.camera_input("Capture an image of the wrist")
        if camera_image is not None:
            with open(dir / "temp_image_cam.jpg", "wb") as f:
                f.write(camera_image.getbuffer())
            img_path = str(dir / 'temp_image_cam.jpg')

    elif option == "Upload Image":
        # Streamlit widget to upload an image
        uploaded_image = st.file_uploader("Upload an image of the wrist", type=["jpg", "jpeg", "png"])
        if uploaded_image is not None:
            with open(dir / "temp_image.jpg", "wb") as f:
                f.write(uploaded_image.getbuffer())
            img_path = str(dir / 'temp_image.jpg')

    # Proceed if either a camera or uploaded image is available
    if (option == "Capture Image" and camera_image) or (option == "Upload Image" and uploaded_image):
        start = time.time()
        # Prepare the file for the request
        files = [
            ('image', (img_path, open(img_path, 'rb'), 'image/jpeg'))
        ]

        payload = {'isEar': 'true', 'isNeck': 'false'}
        headers = {
            'Authorization': f"Bearer {BEARER_TOKEN}"
        }

        # Make the request
        response = requests.request("POST", API_URL, headers=headers, data=payload, files=files, verify=False)

        end = time.time() - start 
        st.write("Time taken:", end)
        results = response.text

        # Load and display the uploaded image
        img = cv2.imread(img_path)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        # Print the response for debugging
        st.write("API Response:", results)

        # Attempt to parse the JSON response
        try:
            data = json.loads(results)
            # Check if 'results' key exists
            if 'results' not in data:
                st.error("API response does not contain 'results' key.")

            ear_data = data["results"].get("ear_coordinates", [])
            zoom_factor = data["results"].get("zoom_factor", 1.0)
            norm_prod_height = data["results"].get("norm_prod_height", 1.0)

            # Handle different formats for ear_coordinates
            ear_pixels_list = []
            if isinstance(ear_data, list) and all(isinstance(coord, list) and len(coord) == 2 for coord in ear_data):
                # List format with coordinates
                ear_pixels_list.append([(int(coord[0] * img.shape[1]), int(coord[1] * img.shape[0])) for coord in ear_data])
            elif isinstance(ear_data, dict):
                # Dictionary format with left and right points
                if 'left' in ear_data and isinstance(ear_data['left'], list):
                    ear_pixels_list.append([(int(coord[0] * img.shape[1]), int(coord[1] * img.shape[0])) for coord in ear_data['left']])
                if 'right' in ear_data and isinstance(ear_data['right'], list):
                    ear_pixels_list.append([(int(coord[0] * img.shape[1]), int(coord[1] * img.shape[0])) for coord in ear_data['right']])
            else:
                st.error("Invalid format for 'ear_coordinates' in API response.")

        except json.JSONDecodeError:
            st.error("Failed to decode JSON from the API response.")

        # Display the image
        st.image(img, width=200)

        # Resize the earring image based on its longest dimension
        obj_np = np.array(obj)
        earring_width = obj_np.shape[1]
        earring_height = obj_np.shape[0]
        longest_side = max(earring_width, earring_height)

        # Determine the resize factor
        is_circular = (earring_width == earring_height)
        resize_factor = 0.025 if is_circular else 0.10
        new_width = int(earring_width * resize_factor)
        new_height = int(earring_height * resize_factor)
        obj_resized = cv2.resize(obj_np, (new_width, new_height), interpolation=cv2.INTER_LINEAR)

        # Rotate the resized earring if needed (assuming no rotation needed for earrings)
        obj_rotated_pil = Image.fromarray(obj_resized, "RGBA")

        # Create a copy of the original image to overlay earrings
        result_img = img.copy()

        # Overlay the earring on the detected ear(s)
        for ear_pixels in ear_pixels_list:
            for (x, y) in ear_pixels:
                center_x = int(x)
                center_y = int(y)
                
                if is_circular:
                    # Overlay from the center
                    top_left_x = int(center_x - new_width // 2)
                    top_left_y = int(center_y - new_height // 2)
                else:
                    # Overlay from the top
                    top_left_x = int(center_x - new_width // 2)
                    top_left_y = int(center_y)  # Align top of earring with ear coordinate

                # Ensure the earring fits within the image bounds
                top_left_x = max(0, top_left_x)
                top_left_y = max(0, top_left_y)

                # Overlay the earring on the ear image
                obj_rotated_cv = np.array(obj_rotated_pil)
                for i in range(new_height):
                    for j in range(new_width):
                        if obj_rotated_cv[i, j][3] > 0:  # Check alpha channel
                            x_pos = top_left_x + j
                            y_pos = top_left_y + i
                            if 0 <= x_pos < img.shape[1] and 0 <= y_pos < img.shape[0]:
                                result_img[y_pos, x_pos] = obj_rotated_cv[i, j][:3]  # Use RGB channels

        st.image(result_img, caption='Ear with Earrings Overlay', use_column_width=True)
