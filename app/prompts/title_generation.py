def get_title_generation_prompt(user_message: str) -> str:
    return f"""
    You are a helpful assistant that generates a concise title for a chat session based on the user's first message.
    The title should be 3-5 words long, summarizing the user's intent.
    Do not use quotes.
    
    User Message: {user_message}
    
    Title:
    """
