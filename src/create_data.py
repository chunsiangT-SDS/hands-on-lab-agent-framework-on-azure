from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv
import asyncio
from agent_framework.azure import AzureAIAgentClient

load_dotenv()


async def create_vector_store(
    client: AzureAIAgentClient,
) -> str:
    """Create a vector store with sample documents."""
    file_path = "./files/contoso-github-issues-guidelines.md"
    file = await client.agents_client.files.upload_and_poll(
        file_path=file_path, purpose="assistants"
    )

    vector_store = await client.agents_client.vector_stores.create_and_poll(
        file_ids=[file.id], name="contoso-github-issues-guidelines-vector-store"
    )
    
    return vector_store.id


async def main():
    async with (
        AzureCliCredential() as credential,
        AzureAIAgentClient(credential=credential) as chat_client,
    ):
        vector_store_id = await create_vector_store(chat_client)
        print(f"Vector store created with ID: {vector_store_id}")


if __name__ == "__main__":
    asyncio.run(main())