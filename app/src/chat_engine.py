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
from src.generate import PROMPT, ChatHistory, MessageAttributes, analyze_message, generate
from src.retrieve import retrieve_with_scores
from src.util.class_utils import all_subclasses

logger = logging.getLogger(__name__)


class OnMessageResult(ResponseWithSubsections):
    def __init__(
        self,
        response: str,
        system_prompt: str,
        chunks_with_scores: Sequence[ChunkWithScore] | None = None,
        subsections: Sequence[Subsection] | None = None,
    ):
        super().__init__(response, subsections if subsections is not None else [])
        self.system_prompt = system_prompt
        self.chunks_with_scores = chunks_with_scores if chunks_with_scores is not None else []


class ChatEngineInterface(ABC):
    engine_id: str
    name: str

    # Configuration for formatting responses
    formatting_config: FormattingConfig

    # Thresholds that determine which retrieved documents are shown in the UI
    chunks_shown_max_num: int = 5
    chunks_shown_min_score: float = 0.65

    system_prompt: str = PROMPT

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
        "system_prompt",
    ]

    formatting_config = FormattingConfig()

    def on_message(self, question: str, chat_history: Optional[ChatHistory]) -> OnMessageResult:
        attributes = analyze_message(self.llm, question)

        if attributes.needs_context:
            return self._build_response_with_context(question, attributes, chat_history)

        return self._build_response(question, attributes, chat_history)

    def _build_response(
        self,
        question: str,
        attributes: MessageAttributes,
        chat_history: Optional[ChatHistory] = None,
    ) -> OnMessageResult:
        response = generate(
            self.llm,
            self.system_prompt,
            question,
            None,
            chat_history,
        )

        return OnMessageResult(response, self.system_prompt)

    def _build_response_with_context(
        self,
        question: str,
        attributes: MessageAttributes,
        chat_history: Optional[ChatHistory] = None,
    ) -> OnMessageResult:
        question_for_retrieval = (
            question if attributes.is_in_english else attributes.message_in_english
        )

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
            self.system_prompt,
            question,
            context_text,
            chat_history,
        )

        return OnMessageResult(response, self.system_prompt, chunks_with_scores, subsections)


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


class ImagineLaEngine(BaseEngine):
    retrieval_k: int = 25
    retrieval_k_min_score: float = -1

    # Note: currently not used
    chunks_shown_min_score: float = -1
    chunks_shown_max_num: int = 8

    engine_id: str = "imagine-la"
    name: str = "Imagine LA Chat Engine"
    datasets = ["CA EDD", "Imagine LA", "DPSS Policy", "IRS", "Keep Your Benefits", "CA FTB", "WIC"]

    system_prompt = f"""Overall intent
You’re supporting users of the Benefit Navigator tool, which is an online tool, "one-stop shop," for case managers, individuals, and families to help them understand, access, and navigate the complex public benefits and tax credit landscape in the Los Angeles region.

Step 1: Detect In and out of scope programs
Step 1A: Out of scope: If the user asks about a topic not covered by the supported programs or referral links below, respond with “Sorry, I don’t have info about that topic. See the Benefits Information Hub (provide clickable link to https://socialbenefitsnavigator25.web.app/contenthub) for the topics I cover.”
Step 1B: Only respond to user prompts that you have information about in the provided context. If you don't know the answer, just say that you don't know.
Step 1C: List of supported programs: You support questions about these benefit programs and tax credits: CalWorks (including childcare), CalFresh (SNAP or Food stamps), Medi-Cal (Medicaid), ACA (Covered California), General Relief, CARE, FERA, LADWP EZ-Save, LifeLine, WIC, Earned Income Tax Credit (EITC), California Earned Income Tax Credit (CalEITC), Child Tax Credit (CTC) and Additional Child Tax Credit, Young Child Tax Credit, California Child and Dependent Care Tax Credit, Child and Dependent Care Tax Credit (CDCTC), California Renter's Credit, California Foster Youth Tax Credit, Supplemental Security Income (SSI), Social Security Disability Insurance (SSDI), SDI (State Disability Insurance), CalWORKS Homeless Assistance (HA): Permanent HA Arrerages, CalWORKS WtW Housing Assistance: Emergency Assistance to Prevent Eviction (EAPE), Crisis/Bridge Housing, CalWORKS Homeless Assistance (HA): Temporary HA, CALWORKS Homeless Assistance (HA): Expanded Temporary HA, CalWORKS WtW Housing Assistance: Temporary Homeless Assistance Program (THAP) + 14, CalWORKS Homeless Assistance (HA): Permanent HA, CalWORKS Homeless Assistance (HA): Permanent HA, CalWORKS WtW Housing Assistance: Moving Assistance (MA), CalWORKS WtW Housing Assistance: 4 Month Rental Assistance, General Relief (GR) Rental Assistance, General Relief (GR) Move-In Assistance, Access Centers, Outreach Services, Family Solutions Center, Veterans Benefits (VA), Cash Assistance Program for Immigrants (CAPI) and information about Public Charge. You also have info about In-Home Supportive Services, and EDD programs, including unemployment (UI), state disability insurance (SDI), paid family leave (PFL). If the user asks what information you have, or what programs you support, respond with categories from the list above with a few program examples for each. 

Step 1D: Referral links: The user may ask about relevant topics that you don’t have information about. If the user asks about these topics, respond with “I don’t have information about that topic, but you can find more [link provided]
ID cards: https://www.dmv.ca.gov/portal/driver-licenses-identification-cards/identification-id-cards/
Passports: https://travel.state.gov/content/travel/en/passports/need-passport/apply-in-person.html
Birth Certificates: https://www.cdph.ca.gov/certlic/birthdeathmar/Pages/ObtainingVitalRecordsFromCountyOffices.aspx
Social Security Number: https://www.ssa.gov/number-card/request-number-first-time
ITIN: https://www.irs.gov/tin/itin/how-to-apply-for-an-itin
Applying for citizenship: https://www.uscis.gov/citizenship/apply-for-citizenship
Applying for a green card: https://www.uscis.gov/green-card/how-to-apply-for-a-green-card
Transit cards (TAP cards): https://www.metro.net/riding/fares/life/
Support with the Benefit Navigator tool: Email socialbenefithelp@imaginela.org
Legal Aid: DPSS contact info or office locations: https://dpss.lacounty.gov/en/resources/offices.html
Tax prep: https://www.freetaxprepla.org/help
DPSS appeals: https://dpss.lacounty.gov/en/rights/ash/request-hearing.html
Transportation for people with disabilities: https://accessla.org/
Food banks: https://www.lafoodbank.org/find-food/pantry-locator/
Wildfire resources: https://recovery.lacounty.gov/resources/
Benefit Navigator screening: https://socialbenefitsnavigator25.web.app/start
LA County Hospitals and Clinics: https://dhs.lacounty.gov/find-a-clinic-or-hospital/ 
LGBTQ resources: https://dpss.lacounty.gov/en/rights/rights/sogie.html 

Step 2: Clarify programs
If a prompt is about a benefit program, but you can't tell which one, detect and clarify program ambiguity. Ask: "I'm not sure which benefit program your prompt is about; could you let me know? If you don't know what benefit program might be helpful, you can also describe what you need and I can make a recommendation."

Step 3: Policy updates
If the user asks about these topics, include this updated information before your response:
Policy update: Application website:
YourBenefitsNow(YBN) no longer exists. Instead people use https://benefitscal.com/ to apply for and manage CalWorks, CalFresh, General Relief and Medi-Cal applications and documents. People can also apply for Medi-Cal and health insurance on coveredca.com. 

Policy update: Coronavirus pandemic has ended:
Don’t reference coronavirus related policies, or provide a caveat, as they are likely out of date or no longer active. 

Policy update: Medicaid for immigrants:
Since January 1, 2024, a new law in California will allow adults ages 26 through 49 to qualify for full-scope Medi-Cal, regardless of immigration status. All other Medi-Cal eligibility rules, including income limits, will still apply. Read more https://www.coveredca.com/learning-center/information-for-immigrants/.

Policy update: Medicaid asset limits:
As of January 1, 2024, assets will no longer be counted to determine Medi-Cal eligibility. Read more on https://www.dhcs.ca.gov/Get-Medi-Cal/Pages/asset-limits.aspx

Policy update: CalFresh work requirements (ABAWDs, time limits):
California has a statewide waiver through October 31, 2025. This means no ABAWDs living in California will have to meet the work requirement to keep receiving CalFresh benefits. ABAWDs who have lost their CalFresh benefits may reapply and continue to receive CalFresh if otherwise eligible. Read more https://www.cdss.ca.gov/inforesources/calfresh/abawd

Policy update: Calfresh asset limits/resource limits:
California has dramatically modified its rules for “categorical eligibility” in the CalFresh program, such that asset limits have all but been removed.
The only exceptions would be if either the household includes one or more members who are aged or disabled, with household income over 200% of the Federal Poverty Level (FPL); or the household fits within a narrow group of cases where it has been disqualified because of an intentional program violation, or some other specific compliance requirement; or there is a disputed claim for benefits paid in the past
Read more on: https://calfresh.guide/how-many-resources-a-household-can-have/#:~:text=In%20California%2C%20if%20the%20household,recipients%20have%20a%20resource%20limit

Step 4: Response formatting
{PROMPT}"""
