# 필요한 라이브러리들을 임포트합니다.
import json
import streamlit as st
from sdk import ChatClient
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader
import yaml
from yaml.loader import SafeLoader
from streamlit_authenticator.utilities.exceptions import LoginError
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


# config.yaml 파일에서 설정값을 로드합니다.
with open('config.yaml') as file:
    config = yaml.load(file, Loader=SafeLoader)

# Dify 클라이언트를 초기화합니다.
client = ChatClient(
    api_key=config['dify']['api_key'],
    base_url=config['dify']['base_url']
)

# 파일 카테고리별 확장자 정의
DIFY_FILE_CATEGORY_EXTENSIONS = {
    "document": [  # 문서 파일 확장자
        "TXT", "MD", "MDX", "MARKDOWN", "PDF", "HTML", "XLSX", "XLS",
        "DOC", "DOCX", "CSV", "EML", "MSG", "PPTX", "PPT", "XML", "EPUB"
    ],
    "image": ["JPG", "JPEG", "PNG", "GIF", "WEBP", "SVG"],  # 이미지 파일 확장자
    "audio": ["MP3", "M4A", "WAV", "WEBM", "AMR", "MPGA"],  # 오디오 파일 확장자
    "video": ["MP4", "MOV", "MPEG", "MPGA"]  # 비디오 파일 확장자
}

# 파일 카테고리 목록
DIFY_FILE_CATEGORIES = list(DIFY_FILE_CATEGORY_EXTENSIONS.keys())


# 파일 이름을 받아 해당 파일의 카테고리를 반환하는 함수
def get_dify_file_category(file_name: str) -> str:
    extension = file_name.split(".")[-1].upper() if "." in file_name else ""
    for category, extensions in DIFY_FILE_CATEGORY_EXTENSIONS.items():
        if extension in extensions:
            return category
    return "custom"  # 정의된 카테고리에 없는 경우 "custom" 반환


# Dify 애플리케이션 파라미터를 로드하는 함수 (60초 캐시)
@st.cache_data(ttl=60)
def load_parameters():
    response = client.get_application_parameters(
        user=st.session_state.get("username"))
    if response.status_code == 200:
        st.session_state.parameters = response.json()
        logger.debug(st.session_state.parameters)
    else:
        st.error(response.text)


# 대화 목록을 로드하는 함수
def load_conversations():
    response = client.get_conversations(
        user=st.session_state.get("username"))
    if response.status_code == 200:
        st.session_state.conversations = response.json()["data"]


# 특정 대화의 메시지들을 로드하는 함수
def load_messages(conversation_id: str | None = None):
    if conversation_id is None:
        return

    response = client.get_conversation_messages(
        user=st.session_state.get("username"),
        conversation_id=conversation_id,
        limit=100
    )
    if response.status_code == 200:
        logger.debug(response.text)
        messages_data = response.json()["data"]
        st.session_state.messages = []
        for msg in messages_data:
            # 사용자 메시지 추가
            st.session_state.messages.append({
                "role": "user",
                "content": msg["query"],
                "message_files": list(filter(lambda x: x["belongs_to"] == "user", msg.get("message_files", [])))
            })
            # 어시스턴트 메시지 추가
            st.session_state.messages.append({
                "role": "assistant",
                "content": msg["answer"] or "\n".join([t["thought"] for t in msg["agent_thoughts"]]),
                "message_files": list(filter(lambda x: x["belongs_to"] != "user", msg.get("message_files", [])))
            })
        logger.debug(st.session_state.messages)


# 파일 업로드 함수
def upload_file(file) -> dict | None:
    response = client.file_upload(
        user=st.session_state.get("username"), files={"file": (file.name, file.read(), file.type)})
    if response.status_code != 201:
        st.error(response.text)
        return None
    return response.json()


# 사이드바 렌더링 함수
def render_sidebar():
    with st.sidebar:

        if icon := config['info'].get('icon'):
            st.logo(icon, size="medium")
        if title := config['info'].get('title'):
            st.title(title)
        else:
            st.title("대화 목록")

        # 새 대화 시작 버튼
        if st.button("새 채팅", use_container_width=True, icon="➕"):
            st.session_state.current_conversation_id = None
            st.session_state.messages = []
            st.rerun()
        st.divider()

        # 대화 목록 표시
        for conv in st.session_state.conversations:
            if st.button(
                conv["name"],
                key=f"conv_{conv['id']}",
                use_container_width=True,
                type="primary" if conv["id"] == st.session_state.current_conversation_id else "secondary"
            ):
                # 선택된 대화의 메시지 로드
                st.session_state.current_conversation_id = conv["id"]
                st.rerun()


# 메인 창 헤더 렌더링 함수
def render_header():
    if icon := config['info'].get('icon'):
        logger.debug(icon)
        st.logo(icon, size="medium")

    if title := config['info'].get('title'):
        st.title(title)
    if description := config['info'].get('description'):
        st.write(description)


# 메시지 렌더링 함수
def render_messages():
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

            # 메시지에 첨부된 파일 렌더링
            if message.get("message_files"):
                for file in message["message_files"]:
                    render_dify_file(file)


def render_dify_file(file: dict):
    if file["type"] == "image":
        st.image(file["url"])
    elif file["type"] == "video":
        st.video(file["url"])
    else:
        st.download_button(
            label=file["id"], data=file["url"], file_name=file["id"])


# 세션 상태 초기화 함수
def init_session_state():
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "current_conversation_id" not in st.session_state:
        st.session_state.current_conversation_id = None
    if "conversations" not in st.session_state:
        st.session_state.conversations = []
    if "parameters" not in st.session_state:
        st.session_state.parameters = {}


# 구글 로그인 처리 함수
def google_login():
    if not config.get('oauth2'):
        return

    authenticator = stauth.Authenticate(
        config['credentials'],
        config['cookie']['name'],
        config['cookie']['key'],
        config['cookie']['expiry_days']
    )
    try:
        authenticator.experimental_guest_login(
            '구글 로그인',
            provider='google',
            oauth2=config['oauth2']
        )
    except Exception as e:
        if isinstance(e, LoginError):
            authenticator.cookie_controller.delete_cookie()
            st.write("로그인 정보가 변경되었습니다. 새로고침 후 다시 시도해주세요.")
            return
        else:
            st.error(e)


# 메인 함수
def main():
    st.set_page_config(layout="wide")  # 페이지 레이아웃 설정

    init_session_state()  # 세션 상태 초기화

    google_login()  # 구글 로그인 처리

    if not st.session_state.get('authentication_status'):
        return

    load_conversations()  # 대화 목록 로드
    load_parameters()  # 파라미터 로드
    load_messages(st.session_state.current_conversation_id)  # 메시지 로드

    render_sidebar()  # 사이드바 렌더링

    render_header()  # 헤더 렌더링
    render_messages()  # 메시지 렌더링

    # 채팅 인터페이스
    opener = st.session_state.parameters.get(
        "opening_statement") or "질문을 입력해주세요"
    file_type = st.session_state.parameters.get(
        "file_upload", {}).get("allowed_file_extensions", [])

    # 채팅 입력 처리
    if prompt := st.chat_input(opener, accept_file=True, file_type=file_type):
        # 사용자 메시지를 채팅 기록에 추가
        st.session_state.messages.append(
            {"role": "user", "content": prompt.text}
        )

        uploaded_files = []
        with st.chat_message("user"):
            st.markdown(prompt.text)

            # 첨부된 파일 처리
            if prompt.files:
                for file in prompt.files:
                    # 파일 업로드
                    result = upload_file(file)
                    if result is None:
                        return
                    file_category = get_dify_file_category(
                        result["name"])
                    uploaded_files.append({
                        "transfer_method": "local_file",
                        "name": result["name"],
                        "upload_file_id": result["id"],
                        "type": file_category,
                    })
                    # 이미지 또는 비디오 파일 렌더링
                    if file_category == "image":
                        st.image(file)
                    elif file_category == "video":
                        st.video(file)
                    else:
                        st.write(f"File uploaded: {result['name']}")

        # 어시스턴트 메시지 추가
        st.session_state.messages.append(
            {"role": "assistant", "content": ""})

        # Dify로부터 응답 받기
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            response_text = ""

            with st.spinner("Thinking..."):
                response = client.create_chat_message(
                    inputs={},
                    query=prompt.text,
                    response_mode="streaming",
                    user=st.session_state.get("username"),
                    conversation_id=st.session_state.current_conversation_id,
                    files=uploaded_files,
                )
                if response.status_code != 200:
                    st.error(response.text)
                    return

                # 스트리밍 응답 처리
                for chunk in response.iter_lines():
                    if not chunk:
                        continue

                    decoded_chunk = chunk.decode("utf-8")
                    logger.debug(decoded_chunk)
                    try:
                        data = json.loads(decoded_chunk.strip()[6:])
                    except json.decoder.JSONDecodeError:
                        continue

                    match data["event"]:
                        case "message":
                            response_text += data["answer"]
                            message_placeholder.markdown(response_text)
                        case "message_end":
                            message_placeholder.markdown(response_text)
                            st.session_state.current_conversation_id = data["conversation_id"]
                        case "agent_message":
                            response_text += data["answer"]
                            message_placeholder.markdown(response_text)
                        case "agent_thought":
                            pass
                        case "message_file":
                            render_dify_file(data)
                        case "error":
                            st.error(data)
                        case _:
                            pass

        st.rerun()  # 리렌더링


if __name__ == "__main__":
    main()
