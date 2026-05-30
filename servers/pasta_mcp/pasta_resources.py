def get_pasta_sample_image() -> bytes:
    '''
    Returns a sample image of pasta in base64 format.
    '''
    with open("servers/pasta_mcp/pasta_img.png", "rb") as file:
        return file.read()