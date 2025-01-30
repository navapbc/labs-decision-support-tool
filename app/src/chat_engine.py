import logging
from abc import ABC, abstractmethod
from typing import Optional, Sequence

from src.citations import (
    CitationFactory,
    ResponseWithSubsections,
    create_prompt_context,
    split_into_subsections,
)
from src.db.models.document import ChunkWithScore, Subsection
from src.format import FormattingConfig
from src.generate import (
    ChatHistory,
    MessageAttributes,
    MessageAttributesT,
    analyze_message,
    generate,
)
from src.retrieve import retrieve_with_scores
from src.util.class_utils import all_subclasses

logger = logging.getLogger(__name__)

# Reminder: If your changes are chat-engine-specific, then update the specific `chat_engine.system_prompt_*`.
ANALYZE_MESSAGE_PROMPT = """Analyze the user's message to respond with a JSON dictionary populated with the following fields.

If the user's message is not in English, set translated_message to be an English translation of the user's message. \
Otherwise, set translated_message to be an empty string.

If the question would be easier to answer with additional policy or program context (such as policy documentation), \
set needs_context to True and canned_response to empty string. \
Otherwise, set needs_context to False.
"""

PROMPT = """Provide answers in plain language using http://plainlanguage.gov guidelines.
Write at the average American reading level.
Use bullet points to structure info. Don't use numbered lists.
Keep your answers as similar to your knowledge text as you can.
Respond in the same language as the user's message.
If the user asks for a list of programs or requirements, list them all, don't abbreviate the list. For example "List housing programs available to youth" or "What are the requirements for students to qualify for CalFresh?"

Citations
When referencing the context, do not quote directly. Use the provided citation numbers (e.g., (citation-1)) to indicate when you are drawing from the context. To cite multiple sources at once, you can append citations like so: (citation-1) (citation-2), etc. For example: 'This is a sentence that draws on information from the context.(citation-1)'

Example Answer:
If the client lost their job at no fault, they may be eligible for unemployment insurance benefits. For example: They may qualify if they were laid off due to lack of work.(citation-1) (citation-2) They might be eligible if their hours were significantly reduced.(citation-3)
"""


class OnMessageResult(ResponseWithSubsections):
    def __init__(
        self,
        response: str,
        system_prompt: str,
        attributes: MessageAttributesT,
        *,
        chunks_with_scores: Sequence[ChunkWithScore] | None = None,
        subsections: Sequence[Subsection] | None = None,
    ):
        super().__init__(response, subsections if subsections is not None else [])
        self.system_prompt = system_prompt
        self.attributes = attributes
        self.chunks_with_scores = chunks_with_scores if chunks_with_scores is not None else []


class ChatEngineInterface(ABC):
    engine_id: str
    name: str

    # Configuration for formatting responses
    formatting_config: FormattingConfig

    # Thresholds that determine which retrieved documents are shown in the UI
    chunks_shown_max_num: int = 5
    chunks_shown_min_score: float = 0.65

    system_prompt_1: str = ANALYZE_MESSAGE_PROMPT
    system_prompt_2: str = PROMPT

    # List of engine-specific configuration settings that can be set by the user.
    # The string elements must match the attribute names for the configuration setting.
    user_settings: list[str]

    def __init__(self) -> None:
        super().__init__()

    @abstractmethod
    def on_message(self, question: str, chat_history: Optional[ChatHistory]) -> OnMessageResult:
        pass


def available_engines() -> list[str]:
    return [
        engine_class.engine_id
        for engine_class in all_subclasses(ChatEngineInterface)
        if hasattr(engine_class, "engine_id") and engine_class.engine_id
    ]


def create_engine(engine_id: str) -> ChatEngineInterface | None:
    if engine_id not in available_engines():
        return None

    chat_engine_class = next(
        engine_class
        for engine_class in all_subclasses(ChatEngineInterface)
        if hasattr(engine_class, "engine_id") and engine_class.engine_id == engine_id
    )
    return chat_engine_class()


# Subclasses of ChatEngineInterface can be extracted into a separate file if it gets too large
class BaseEngine(ChatEngineInterface):
    datasets: list[str] = []
    llm: str = "gpt-4o"

    # Thresholds that determine which documents are sent to the LLM
    retrieval_k: int = 8
    retrieval_k_min_score: float = 0.45

    user_settings = [
        "llm",
        "retrieval_k",
        "retrieval_k_min_score",
        "chunks_shown_max_num",
        "chunks_shown_min_score",
        "system_prompt_1",
        "system_prompt_2",
    ]

    formatting_config = FormattingConfig()

    def on_message(self, question: str, chat_history: Optional[ChatHistory]) -> OnMessageResult:
        attributes = analyze_message(self.llm, self.system_prompt_1, question, MessageAttributes)

        if attributes.needs_context:
            return self._build_response_with_context(question, attributes, chat_history)

        return self._build_response(question, attributes, chat_history)

    def _build_response(
        self,
        question: str,
        attributes: MessageAttributesT,
        chat_history: Optional[ChatHistory] = None,
    ) -> OnMessageResult:
        response = generate(
            self.llm,
            self.system_prompt_2,
            question,
            None,
            chat_history,
        )

        return OnMessageResult(response, self.system_prompt_2, attributes)

    def _build_response_with_context(
        self,
        question: str,
        attributes: MessageAttributesT,
        chat_history: Optional[ChatHistory] = None,
    ) -> OnMessageResult:
        question_for_retrieval = attributes.translated_message or question

        chunks_with_scores = retrieve_with_scores(
            question_for_retrieval,
            retrieval_k=self.retrieval_k,
            retrieval_k_min_score=self.retrieval_k_min_score,
            datasets=self.datasets,
        )

        chunks = [chunk_with_score.chunk for chunk_with_score in chunks_with_scores]
        # Provide a factory to reset the citation id counter
        subsections = split_into_subsections(chunks, factory=CitationFactory())
        context_text = create_prompt_context(subsections)

        response = generate(
            self.llm,
            self.system_prompt_2,
            question,
            context_text,
            chat_history,
        )

        return OnMessageResult(
            response,
            self.system_prompt_2,
            attributes,
            chunks_with_scores=chunks_with_scores,
            subsections=subsections,
        )


class CaEddWebEngine(BaseEngine):
    retrieval_k: int = 50
    retrieval_k_min_score: float = -1

    # Note: currently not used
    chunks_shown_min_score: float = -1
    chunks_shown_max_num: int = 8

    engine_id: str = "ca-edd-web"
    name: str = "CA EDD Web Chat Engine"
    datasets = ["CA EDD"]

    system_prompt = f"""You are an assistant to navigators who support clients (such as claimants, beneficiaries, families, and individuals) during the screening, application, and receipt of public benefits from California's Employment Development Department (EDD).
If you can't find information about the user's prompt in your context, don't answer it. If the user asks a question about a program not delivered by California's Employment Development Department (EDD), don't answer beyond pointing the user to the relevant trusted website for more information. Don't answer questions about tax credits (such as EITC, CTC) or benefit programs not delivered by EDD.
If a prompt is about an EDD program, but you can't tell which one, detect and clarify program ambiguity. Ask: "The EDD administers several programs such as State Disability Insurance (SDI), Paid Family Leave (PFL), and Unemployment Insurance (UI). I'm not sure which benefit program your prompt is about; could you let me know?"

{PROMPT}"""


class ImagineLA_MessageAttributes(MessageAttributes):
    canned_response: str
    alert_message: str


class ImagineLaEngine(BaseEngine):
    retrieval_k: int = 25
    retrieval_k_min_score: float = -1

    # Note: currently not used
    chunks_shown_min_score: float = -1
    chunks_shown_max_num: int = 8

    user_settings = [
        "llm",
        "retrieval_k",
        "retrieval_k_min_score",
        "system_prompt_1",
        "system_prompt_2",
    ]

    engine_id: str = "imagine-la"
    name: str = "Imagine LA Chat Engine"
    datasets = [
        "CA EDD",
        "Imagine LA",
        "DPSS Policy",
        "IRS",
        "Keep Your Benefits",
        "CA FTB",
        "WIC",
        "Covered California",
    ]

    system_prompt_1 = """Analyze the user's message to respond with a JSON dictionary populated with the following fields and default values:
- canned_response: empty string
- alert_message: empty string
- needs_context: True
- translated_message: empty string

The canned_response string should be in the same language as the user's question. \
If canned_response is set to a non-empty string, leave the other JSON fields as their default values.

Supported benefit programs are:
- CalWORKS (including childcare), CalFresh, Medi-Cal (Medicaid), ACA (Covered California),
- CalWORKS Homeless Assistance (HA) for Permanent HA, Permanent HA Arrerages, Expanded Temporary HA,
- CalWORKS WtW Housing Assistance: Emergency Assistance to Prevent Eviction (EAPE),
- CalWORKS WtW Housing Assistance: Temporary Homeless Assistance Program (THAP or Temporary HA) + 14, CalWORKS Homeless Assistance (HA): Permanent HA,
- CalWORKS WtW Housing Assistance: Moving Assistance (MA),
- CalWORKS WtW Housing Assistance: 4 Month Rental Assistance, General Relief (GR) Rental Assistance, General Relief (GR) Move-In Assistance,
- Crisis/Bridge Housing, General Relief, CARE, FERA, LADWP EZ-Save, LifeLine, WIC,
- Earned Income Tax Credit (EITC), California Earned Income Tax Credit (CalEITC), Child Tax Credit (CTC) and Additional Child Tax Credit, Young Child Tax Credit,
- California Child and Dependent Care Tax Credit, Child and Dependent Care Tax Credit (CDCTC), California Renter's Credit, California Foster Youth Tax Credit,
- Supplemental Security Income (SSI), Social Security Disability Insurance (SSDI), SDI (State Disability Insurance),
- Access Centers, Outreach Services, Family Solutions Center, Veterans Benefits (VA), Cash Assistance Program for Immigrants (CAPI)
- Public Charge, In-Home Supportive Services, and EDD programs
- unemployment insurance (UI), state disability insurance (SDI), paid family leave (PFL)

If the user asks what programs are supported or what information is available, \
set canned_response to text that gives examples and describes categories for the supported benefit programs.

If the user's question is not about a supported benefit program, set canned_response to one of the following based on the condition:
Condition 1: If the user's question is about a referral link below, set canned_response to \
"I don't have information about that topic, but you can find more at [link provided]", \
where [link provided] is one or more of the referral links below.
Condition 2: Otherwise set canned_response to "Sorry, I don't have info about that topic. See the [Benefits Information Hub](https://socialbenefitsnavigator25.web.app/contenthub) for the topics I cover."

Referral links:
- ID cards: https://www.dmv.ca.gov/portal/driver-licenses-identification-cards/identification-id-cards/
- Passports: https://travel.state.gov/content/travel/en/passports/need-passport/apply-in-person.html
- Birth Certificates: https://www.cdph.ca.gov/certlic/birthdeathmar/Pages/ObtainingVitalRecordsFromCountyOffices.aspx
- Social Security Number: https://www.ssa.gov/number-card/request-number-first-time
- ITIN: https://www.irs.gov/tin/itin/how-to-apply-for-an-itin
- Applying for citizenship: https://www.uscis.gov/citizenship/apply-for-citizenship
- Applying for a green card: https://www.uscis.gov/green-card/how-to-apply-for-a-green-card
- Transit cards (TAP cards): https://www.metro.net/riding/fares/life/
- Support with the Benefit Navigator tool: Email socialbenefithelp@imaginela.org
- Legal Aid: DPSS contact info or office locations: https://dpss.lacounty.gov/en/resources/offices.html
- Tax prep: https://www.freetaxprepla.org/help
- DPSS appeals: https://dpss.lacounty.gov/en/rights/ash/request-hearing.html
- Transportation for people with disabilities: https://accessla.org/
- Food banks: https://www.lafoodbank.org/find-food/pantry-locator/
- Wildfire resources: https://recovery.lacounty.gov/resources/
- Benefit Navigator screening: https://socialbenefitsnavigator25.web.app/start
- LA County Hospitals and Clinics: https://dhs.lacounty.gov/find-a-clinic-or-hospital/
- LGBTQ resources: https://dpss.lacounty.gov/en/rights/rights/sogie.html

If the user's question is related to any of the following policy updates listed below, set canned_response to empty string and \
set alert_message to one or more of the following text based on the user's question: 
- Benefits application website: "YourBenefitsNow(YBN) no longer exists. Instead people use [benefitscal.com](https://benefitscal.com/) to apply for and manage \
CalWorks, CalFresh, General Relief and Medi-Cal applications and documents. People can also apply for Medi-Cal and health insurance at coveredca.com."
- Medicaid for immigrants: "Since January 1, 2024, a new law in California will allow adults ages 26 through 49 to qualify for full-scope Medi-Cal, \
regardless of immigration status. All other Medi-Cal eligibility rules, including income limits, will still apply. \
[Read more](https://www.coveredca.com/learning-center/information-for-immigrants/)."
- Medicaid asset limits: "As of January 1, 2024, assets will no longer be counted to determine Medi-Cal eligibility. \
[Read more](https://www.dhcs.ca.gov/Get-Medi-Cal/Pages/asset-limits.aspx)"
- CalFresh work requirements (ABAWDs, time limits): "California has a statewide waiver through October 31, 2025. This means no ABAWDs living in California \
will have to meet the work requirement to keep receiving CalFresh benefits. \
ABAWDs who have lost their CalFresh benefits may reapply and continue to receive CalFresh if otherwise eligible. \
[Read more](https://www.cdss.ca.gov/inforesources/calfresh/abawd)"
- Calfresh asset limits/resource limits: "California has dramatically modified its rules for 'categorical eligibility' in the CalFresh program, such that asset limits have all but been removed. \
The only exceptions would be if either the household includes one or more members who are aged or disabled, \
with household income over 200% of the Federal Poverty Level (FPL); or the household fits within a narrow group of cases \
where it has been disqualified because of an intentional program violation, or some other specific compliance requirement; or there is a disputed claim for benefits paid in the past. \
[Read more](https://calfresh.guide/how-many-resources-a-household-can-have/#:~:text=In%20California%2C%20if%20the%20household,recipients%20have%20a%20resource%20limit)"

If the user's question is to translate text, set needs_context to False.

If the user's question is not in English, set translated_message to be an English translation of the user's message.
"""

    system_prompt_2 = f"""You're supporting users of the Benefit Navigator tool, which is an online tool, "one-stop shop," for case managers, individuals, and \
families to help them understand, access, and navigate the complex public benefits and tax credit landscape in the Los Angeles region.

If the user's question is about the Coronavirus pandemic, don't reference coronavirus related policies, or provide a caveat, as they are likely out of date or no longer active.

Only respond to the user's question if there is relevant information in the provided context. Otherwise, respond with "I don't know".

{PROMPT}"""

    def on_message(self, question: str, chat_history: Optional[ChatHistory]) -> OnMessageResult:
        attributes = analyze_message(
            self.llm, self.system_prompt_1, question, response_format=ImagineLA_MessageAttributes
        )

        if attributes.alert_message:
            attributes.alert_message = f"**Policy update**: {attributes.alert_message}\n\nThe rest of this answer may be outdated."

        if attributes.canned_response:
            return OnMessageResult(attributes.canned_response, self.system_prompt_1, attributes)

        if attributes.needs_context:
            return self._build_response_with_context(question, attributes, chat_history)

        return self._build_response(question, attributes, chat_history)
