import os
import asyncio
import json
import time
from datetime import datetime
from tavily import TavilyClient
from openai import AsyncOpenAI

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

class AISearch:
    def __init__(self):
        self.tavily = TavilyClient(api_key=TAVILY_API_KEY)
        self.oai = AsyncOpenAI(api_key=OPENAI_API_KEY)
        self.gai = AsyncOpenAI(base_url="https://api.groq.com/openai/v1", api_key=GROQ_API_KEY)
        self.cache = {}
        self.max_retries = 2
        self.current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    async def _call_gpt(self, prompt, json_format=False, quick=False):
        if quick:
            response = await self.gai.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                response_format=(
                    {"type": "json_object"} if json_format else {"type": "text"}
                ),
            )
            return response.choices[0].message.content.strip()


        response = await self.oai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            response_format=(
                {"type": "json_object"} if json_format else {"type": "text"}
            ),
        )
        return response.choices[0].message.content.strip()

    async def _web_search(self, query):
        if query in self.cache:
            return self.cache[query]

        result = self.tavily.search(
            query=query, search_depth="advanced", max_results=6, include_answer=True
        )

        formatted = []
        for i, res in enumerate(result["results"]):
            formatted.append(
                f"Title: {res['title']} URL: {res['url']} Content: {res['content'][:250]}..."
            )
        self.cache[query] = "\n\n".join(formatted)
        return self.cache[query]

    async def _generate_initial_answer(self, query, skip = False, quick = False):
        if skip:
            return f""
        prompt = f"""Today is {self.current_date}. Generate a preliminary answer to this question:
        {query}
        
        Include:
        1. Key points you already know
        2. Potential data needed
        3. Suggested structure
        
        Example for "NVIDIA's 2024 financial report":
        - Known: NVIDIA dominates AI chip market
        - Needed: Q4 revenue growth rate, net profit margin
        - Structure: Market context -> Financial numbers -> Analyst opinions"""

        return await self._call_gpt(prompt, quick=quick)

    async def _breakdown_question(self, query, quick=False):
        prompt = f"""Today is {self.current_date}. Break down this complex question into 2-4 sub-questions. 
        When breaking down the questions, consider the different aspects that need to be covered to provide a comprehensive answer.

        You are encouraged to generate sub-questions with different language as the original question, if you think it will help to get a better answer.
        Follow this template as json format:
        {{
            "sub_questions": [
                "subquestion1",
                "subquestion2"
            ],
            "reasoning": "step-by-step explanation"
        }}
        
        Example Input: "How did NVIDIA's Q4 2024 financial performance compare to competitors?"
        Example Output: {{
            "sub_questions": [
                "NVIDIA Q4 2024 revenue figures",
                "AMD Q4 2024 GPU market share",
                "Analyst comparison of AI chip manufacturers 2024"
            ],
            "reasoning": "Breakdown focuses on financial metrics, market share, and expert analysis for accurate comparison"
        }}

        Example Input: "谁是C罗？"
        # Chinese question, but the sub-questions can be in English (but not all the time)
        Example Output: {{
            "sub_questions": [
                "Who is Cristiano Ronaldo?",
                "What are Cristiano Ronaldo's achievements?"
                "C罗是否访问过中国？"
            ],
            "reasoning": "Breakdown focuses on financial metrics, market share, and expert analysis for accurate comparison"
        }}

        Example Input: "What is the capital of China?"
        # English question, but the sub-questions can be in Chinese (but not all the time)
        Example Output: {{
            "sub_questions": [
                "中国的首都是什么？",
                "北京有什么名胜古迹？",
                "北京的气候如何？"
            ],
            "reasoning": "Breakdown focuses on financial metrics, market share, and expert analysis for accurate comparison"
        }}

        
        Current Question: {query}"""

        response = await self._call_gpt(prompt, json_format=True, quick=quick)
        return json.loads(response)

    async def _evaluate_answer(self, query, answer, skip=False, quick=False):
        if skip:
            return {
            "score": 10,
            "feedback": "Skipped evaluation",
        }

        prompt = f"""Today is {self.current_date}. Evaluate this answer using these criteria:
        1. Factual accuracy (verify against known facts)
        2. Source citation quality (markdown links [title](url))
        3. Structure (clear sections with headings)

        However, if the answer contains information that is closely related to time-sensitive events, please ignore the factual accuracy.
        For example, if the question is about the latest news, the answer should be evaluated based on the structure and source citation quality only, and not the factual accuracy.
        
        Follow this format as json format:
        {{
            "score": 0-10,
            "feedback": "summary of evaluation",
            "detailed": {{
                "strengths": ["list"],
                "weaknesses": ["list"],
                "improvements": ["suggestions"]
            }}
        }}
        
        Example Evaluation:
        {{
            "score": 8,
            "feedback": "Accurate data but needs better source organization",
            "detailed": {{
                "strengths": ["Correct revenue figures", "Good market context"],
                "weaknesses": ["Missing Q4 comparisons", "Uncited market share data"],
                "improvements": ["Add 2023 vs 2024 growth rates", "Link to official financial reports"]
            }}
        }}
        
        Question: {query}
        Answer: {answer}"""

        return json.loads(await self._call_gpt(prompt, json_format=True, quick=quick))

    async def _synthesize_answer(self, query, contexts, initial_ans, feedback=None, quick=False):
        prompt = f"""Today is {self.current_date}. Combine these elements into a final answer:
        
        [Question]
        {query}
        
        [Initial Analysis by LLM (could not be accurate)]
        {initial_ans}
        
        [Research Context]
        {contexts}
        
        {f"[Previous Feedback] {feedback}" if feedback else ""}
        
        Requirements:
        1. Use markdown formatting
        2. Cite sources as [Title](url)
        3. Include data points from research
        4. Current date: {self.current_date}
        5. use same language as the original question
        6. You have to create a reference list at the end, see the example.
        
        Example Structure:
        ## Overview
        Market context... [1](https://...) --> in text citation, 1 is the reference number to [NVIDIA Newsroom](https://...) in reference list
        
        ## Financial Performance
        - Q4 Revenue: $22.1B [1](https://...)
        - Net Margin: 56% [2](https://...)
        
        ## Analysis
        "The growth reflects..." [3](https://...)

        ## References
        1. [NVIDIA Newsroom](https://...)
        2. [Bloomberg](https://...)
        3. [Financial Times](https://...)
        """

        return await self._call_gpt(prompt, quick=quick)
    
    async def _validate_answer(self, query, answer, quick=False):
        prompt = f"""Today is {self.current_date}. Validate this answer based on the following criteria:
        
        Requirements:
        1. Ensure that the answer strictly follow the markdown format.
        2. Ensure that the citation format follows below:
        Example:
        This is a sentence. [1](https://...) --> in text citation, 1 is the reference number to [Title 1](https://...) in reference list

        At the end of the answer, there should be a reference list with the following format:
        ## References
        1. [Title 1](url)
        2. [Title 2](url)

        The reference list should be in the same order as the in-text citations.

        If incorrect [] and () are used, e.g. 【】 and （）, correct them.

        3. Ensure that the answer is relevant to the question.
        4. Ensure that the answer follows the language that the question was asked in. If wrong language is used, correct it.

        Question: {query}
        Answer: {answer}

        Now, please give back the answer that you validated and polished only, without the validation instructions or feedback."""

        return await self._call_gpt(prompt, quick=quick)

    async def search(self, query):
        timer = time.time()
        initial_ans, breakdown = await asyncio.gather(
            self._generate_initial_answer(query, skip=True),
            self._breakdown_question(query, quick=False),
        )
        print(f"Time taken for init answer and breakdown: {time.time() - timer}")
        # print(f"Question Breakdown: {json.dumps(breakdown, indent=2)}")

        best = None
        attempts = 0

        while attempts <= self.max_retries:
            if attempts == 0:
                search_results = await asyncio.gather(
                    *[self._web_search(q) for q in breakdown["sub_questions"]]
                )
                context = "\n\n".join(search_results)
                print(f"Time taken for searching: {time.time() - timer}")

            answer = await self._synthesize_answer(
                query, context, initial_ans, feedback=best["feedback"] if best else None, quick=True
            )

            print(f"Time taken for synth: {time.time() - timer}")

            answer = await self._validate_answer(query, answer, quick=True)

            print(f"Time taken for validate: {time.time() - timer}")

            evaluation = await self._evaluate_answer(query, answer, skip=True)

            print(f"Time taken for eval: {time.time() - timer}")
            # print(
            #     f"Attempt {attempts+1} Evaluation: {json.dumps(evaluation, indent=2)}"
            # )

            if not best or evaluation["score"] > best["score"]:
                sources = list(
                    set(
                        line.split("URL: ")[1]
                        for res in search_results
                        for line in res.split("\n")
                        if line.startswith("URL:")
                    )
                )[:5]

                best = {
                    "answer": answer,
                    "score": evaluation["score"],
                    "feedback": evaluation,
                    "sources": sources,
                }

            if evaluation["score"] >= 6 or attempts >= self.max_retries:
                break

            attempts += 1

        print(f"Total time taken: {time.time() - timer}")
        return {
            "answer": best["answer"],
            "sources": best["sources"],
            "evaluation": best["feedback"],
        }

    async def quick_search(self, query):
        # use openai to quickly generate a response based on websearch
        websearch = await self._web_search(query)
        prompt = f"""Today is {self.current_date}. Answer the question based on the following web search results:
        {websearch}

        Question: {query}"""
        result = await self._call_gpt(prompt)
        return result
