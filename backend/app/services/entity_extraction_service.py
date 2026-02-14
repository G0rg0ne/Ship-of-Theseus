from langchain_openai import ChatOpenAI
from langchain.output_parsers import PydanticOutputParser
from langchain.prompts import PromptTemplate
from app.schemas.entities import ExtractedEntities

class EntityExtractionService:
    """LangChain-based entity extraction."""
    
    def __init__(self, api_key: str, model: str):
        self.llm = ChatOpenAI(
            model=model,
            temperature=0,
            openai_api_key=api_key
        )
        self.parser = PydanticOutputParser(pydantic_object=ExtractedEntities)
    
    def extract_entities(self, text: str, chunk_id: int = 0) -> ExtractedEntities:
        prompt = PromptTemplate(
            template="""Extract structured entities from the following text.
            
            {format_instructions}
            
            Text:
            {text}
            """,
            input_variables=["text"],
            partial_variables={"format_instructions": self.parser.get_format_instructions()}
        )
        
        chain = prompt | self.llm | self.parser
        result = chain.invoke({"text": text})
        result.chunk_id = chunk_id
        return result