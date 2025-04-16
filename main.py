import json
import logging
import os
import streamlit as st
from sdk import ChatClient
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Dify client
client = ChatClient(
    api_key=os.getenv("DIFY_API_KEY"),
    base_url=os.getenv("DIFY_BASE_URL", "https://api.dify.ai/v1")
)

# File category definitions
DIFY_FILE_CATEGORY_EXTENSIONS = {
    "document": [
        "TXT", "MD", "MDX", "MARKDOWN", "PDF", "HTML", "XLSX", "XLS",
        "DOC", "DOCX", "CSV", "EML", "MSG", "PPTX", "PPT", "XML", "EPUB"
    ],
    "image": ["JPG", "JPEG", "PNG", "GIF", "WEBP", "SVG"],
    "audio": ["MP3", "M4A", "WAV", "WEBM", "AMR", "MPGA"],
    "video": ["MP4", "MOV", "MPEG", "MPGA"]
}

DIFY_FILE_CATEGORIES = list(DIFY_FILE_CATEGORY_EXTENSIONS.keys())


def get_dify_file_category(file_name: str) -> str:
    extension = file_name.split(".")[-1].upper() if "." in file_name else ""
    for category, extensions in DIFY_FILE_CATEGORY_EXTENSIONS.items():
        if extension in extensions:
            return category
    return "custom"


def main():
    st.title("Dify Chat Interface")

    # Initialize chat history
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Display chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    response = client.get_application_parameters(user="streamlit-user")
    if response.status_code == 200:
        parameters = response.json()
        _ = """
        parameters = {
            'opening_statement': '어떤 도움이 필요하신가요?',
            'suggested_questions': ['배송상태 조회', '환불/교환 요청'],
            'suggested_questions_after_answer': {'enabled': False},
            'speech_to_text': {'enabled': False},
            'text_to_speech': {'enabled': False, 'voice': '', 'language': ''},
            'retriever_resource': {'enabled': True},
            'annotation_reply': {'enabled': False},
            'more_like_this': {'enabled': False},
            'user_input_form': [],
            'sensitive_word_avoidance': {'enabled': False, 'type': '', 'configs': []},
            'file_upload': {'image': {
                'detail': 'high',
                'enabled': False,
                'number_limits': 3,
                'transfer_methods': ['remote_url', 'local_file']},
                'enabled': False,
                'allowed_file_types': [],
                'allowed_file_extensions': ['.JPG', '.JPEG', '.PNG', '.GIF', '.WEBP', '.SVG', '.MP4', '.MOV', '.MPEG', '.MPGA'],
                'allowed_file_upload_methods': ['remote_url', 'local_file'],
                'number_limits': 3},
            'system_parameters': {
                'image_file_size_limit': 10,
                'video_file_size_limit': 100,
                'audio_file_size_limit': 50,
                'file_size_limit': 15,
                'workflow_file_upload_limit': 10
            }
        }
        """
        # print(parameters)
    else:
        st.error(response.text)

    # Chat input
    if prompt := st.chat_input(parameters["opening_statement"], accept_file=True, file_type=parameters["file_upload"]["allowed_file_extensions"]):
        # Add user message to chat history
        st.session_state.messages.append(
            {"role": "user", "content": prompt.text})

        uploaded_files = []
        with st.chat_message("user"):
            st.markdown(prompt.text)
            if prompt.files:
                for file in prompt.files:
                    response = client.file_upload(
                        user="streamlit-user", files={"file": (file.name, file.read(), file.type)})
                    if response.status_code == 201:
                        file_obj = response.json()
                        file_category = get_dify_file_category(
                            file_obj["name"])
                        uploaded_files.append({
                            "transfer_method": "local_file",
                            "name": file_obj["name"],
                            "upload_file_id": file_obj["id"],
                            "type": file_category,
                        })
                        if file_category == "image":
                            st.image(file)
                        elif file_category == "video":
                            st.video(file)
                        else:
                            st.write(f"File uploaded: {file_obj['name']}")
                    else:
                        st.error(response.text)

        # Get response from Dify
        with st.chat_message("assistant"):
            thoughts_placeholder = st.empty()
            message_placeholder = st.empty()
            response_text = ""
            with st.spinner("Thinking..."):
                response = client.create_chat_message(
                    inputs={},
                    query=prompt.text,
                    response_mode="streaming",
                    user="streamlit-user",
                    conversation_id=None,
                    files=uploaded_files,
                )
                agent_thoughts = []
                if response.status_code == 200:
                    for chunk in response.iter_lines():
                        if chunk:
                            try:
                                data = json.loads(
                                    chunk.decode("utf-8").strip()[6:])
                            except json.decoder.JSONDecodeError:
                                break
                            print(data)
                            match data["event"]:
                                case "message":
                                    response_text += data["answer"]
                                    message_placeholder.markdown(response_text)
                                case "message_end":
                                    message_placeholder.markdown(response_text)
                                case "agent_message":
                                    response_text += data["answer"]
                                    message_placeholder.markdown(response_text)
                                case "agent_thought":
                                    if len(agent_thoughts) == 0:
                                        agent_thoughts.append(data)
                                    else:
                                        last_thought = agent_thoughts[-1]
                                        if last_thought["id"] == data["id"]:
                                            agent_thoughts[-1] = data
                                        else:
                                            agent_thoughts.append(data)

                                    with thoughts_placeholder:
                                        for thought in agent_thoughts:
                                            st.write(thought)
                                        # for thought in agent_thoughts:
                                        #     status_placeholder = st.empty()  # Placeholder to show the tool's status
                                        #     with status_placeholder.status("Thinking...", expanded=True) as s:
                                        #         st.write(thought)
                                        #         s.update(label="Completed Thinking!", expanded=False)  # Update the status once done

                                case "error":
                                    st.error(data)
                                case _:
                                    pass
                else:
                    st.error(response.text)

        # Add assistant response to chat history
        st.session_state.messages.append(
            {"role": "assistant", "content": response_text})


if __name__ == "__main__":
    main()
