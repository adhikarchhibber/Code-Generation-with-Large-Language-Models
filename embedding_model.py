#!/usr/bin/env python
# Embedding-based NL-to-SQL using trained model (primary implementation)

import pandas as pd
from sentence_transformers import SentenceTransformer
import re
import spacy
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
import time
import requests
import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    # .env loading is optional; ignore if python-dotenv not installed
    pass


class EmbeddingNLToSQL:
    def __init__(self, training_data_path=None, remote_url: str | None = None):
        """
        Initialize embedding-based NL-to-SQL converter

        Args:
            training_data_path: Path to training_data.csv with Query and SQL columns
            use_mistral: If True, use Mistral to refine the retrieved SQL
            mistral_model: Name of Ollama model to use (default: "mistral")
            api_mode: 'ollama' (default) to call local Ollama; 'remote' to call custom HTTP API
            remote_url: When api_mode='remote', the endpoint to POST {"prompt": prompt}
        """
        self.model_name = "SentenceTransformer + Remote LLM"
        self.training_data_path = training_data_path or "training_data.csv"
        self.last_prompt = None
        # API endpoint
        self.remote_llm_url = remote_url or os.getenv("LLM_API_URL")
        # Normalize remote URL to include /prompt if missing
        if self.remote_llm_url:
            url = self.remote_llm_url.strip()
            if url.endswith('/'):
                url = url + 'prompt'
            elif '/prompt' not in url.split('?', 1)[0]:
                url = url.rstrip('/') + '/prompt'
            self.remote_llm_url = url

        # Load NLP model for POS tagging
        #self.nlp = spacy.load("en_core_web_sm")
        """
        # Known schema tokens (column names)
        #self.schema_tokens = [
            "geometry", "statefp", "countyfp", "countyns", "geoid", "name", "namelsad",
            "lsad", "classfp", "mtfcc", "csafp", "cbsafp", "metdivfp", "funcstat",
            "aland", "awater", "intptlat", "intptlon", "state", "stateaabrv"
        ]

        # Load embedding model
        self.model = SentenceTransformer("all-MiniLM-L6-v2")

        # Training data and embeddings
        self.df = None
        self.training_embeddings = None
        self.questions = None
        self.sql_column = None  # 'Answer' or 'SQL'

        # Load training data if available
        self._load_training_data()
        """
    def _load_training_data(self):
        """Load and embed training data"""
        try:
            self.df = pd.read_csv(self.training_data_path)

            if 'Answer' in self.df.columns:
                self.sql_column = 'Answer'
            elif 'SQL' in self.df.columns:
                self.sql_column = 'SQL'
            else:
                raise ValueError("CSV must have either 'Answer' or 'SQL' column")

            self.questions = self.df['Query'].tolist()

            masked_questions = []
            for q in self.questions:
                masked_q, _ = self.mask_schema_tokens(q, use_pos_weight=True)
                masked_questions.append(masked_q)

            self.training_embeddings = self.model.encode(masked_questions, convert_to_tensor=True)

            print(f"Loaded {len(self.questions)} training examples")
            print(f"Using column '{self.sql_column}' for SQL answers")

        except FileNotFoundError:
            print(f"Training data not found at {self.training_data_path}")
            print("   Model will run in degraded mode. Please update the path.")
            self.df = None
            self.training_embeddings = None
            self.questions = None
            self.sql_column = None
        except Exception as e:
            print(f"Error loading training data: {e}")
            self.df = None
            self.training_embeddings = None
            self.questions = None
            self.sql_column = None

    def mask_schema_tokens(self, question, use_pos_weight=True):
        """
        Mask schema-related tokens in the question.
        Optionally give higher weight to nouns and numbers via POS tags.
        Returns: masked_question, token_weights
        """
        doc = self.nlp(question)
        masked_tokens = []
        token_weights = []

        for token in doc:
            tok_text = token.text
            if any(re.fullmatch(t, tok_text, flags=re.IGNORECASE) for t in self.schema_tokens):
                masked_tokens.append("[MASK]")
            else:
                masked_tokens.append(tok_text)

            if use_pos_weight:
                if token.pos_ in ["NOUN", "PROPN", "NUM"]:
                    token_weights.append(1.0)
                else:
                    token_weights.append(0.0)
            else:
                token_weights.append(1.0)

        masked_question = " ".join(masked_tokens)
        return masked_question, token_weights

    def find_most_similar(self, user_query, top_k=1):
        """Return top_k most similar examples as dicts with query/sql/similarity"""
        if self.training_embeddings is None:
            return []
        if self.questions is None or self.df is None or self.sql_column is None:
            return []

        masked_query, _ = self.mask_schema_tokens(user_query, use_pos_weight=True)
        query_embedding = self.model.encode([masked_query], convert_to_tensor=True)

        similarities = cosine_similarity(
            query_embedding.cpu().numpy(),
            self.training_embeddings.cpu().numpy()
        )[0]

        top_indices = np.argsort(similarities)[-top_k:][::-1]

        results = []
        for idx in top_indices:
            results.append({
                'query': self.questions[idx],
                'sql': self.df.iloc[idx][self.sql_column],
                'similarity': float(similarities[idx])
            })
        return results

    def convert(self, nl_query):
        """
        Convert natural language to SQL using embedding similarity + optional Mistral refinement.
        Returns a dict including the LLM prompt when applicable.
        """
        start_time = time.time()

        builder_url = "http://nasopharyngeal-thriftily-stevie.ngrok-free.dev/prompt"
        generator_url = "http://vulcanological-alverta-unvivaciously.ngrok-free.dev/prompt"

        response = requests.post(builder_url, json={"prompt": nl_query}, timeout=45)
        print(time.time() - start_time)

        reply = response.json()["received"]

        print("Prompt built\n")
        print(reply)

        sql_generated = requests.post(generator_url, json = {"prompt": reply}, timeout = 45).json()['received']
        end_time = time.time()
        print("SQL GENERATED\n")
        print(sql_generated)

        result = {
        "sql" : sql_generated,
        "llm_prompt" : reply,
        "generation_time" : end_time - start_time,
        "success" : True
        }

        return result







    def _refine_with_remote_llm(self, nl_query, similar_examples):
        """
        Use the remote LLM API to refine/adapt SQL based on similar examples

        Args:
            nl_query: User's natural language question
            similar_examples: List of similar examples from training data

        Returns:
            Refined SQL query or None if failed
        """
        try:
            # Build prompt first half with PostGIS reference
            prompt_first_half = """You are an expert in the PostGIS spatial database and highly skilled in writing SQL queries for geographic analysis.

PostGIS extends PostgreSQL with spatial data types and functions.
Below is a quick reference of commonly used spatial functions and their meanings:

- ST_Within(geomA, geomB): Returns TRUE if geometry A is completely within geometry B.
- ST_Intersects(geomA, geomB): Returns TRUE if geometry A and B share any portion of space.
- ST_Distance(geomA, geomB): Returns the minimum distance between geometries A and B, in the same units as the spatial reference system.
- ST_Length(geometry): Returns the length of a LineString in its spatial reference units.
- ST_Area(geometry): Returns the area of a Polygon.
- ST_Contains(geomA, geomB): Returns TRUE if geometry A contains geometry B.
- ST_Union(geomA, geomB): Returns a geometry that represents the union of geomA and geomB.
- ST_Centroid(geometry): Returns the geometric center of a geometry.
- ST_Buffer(geometry, distance): Returns a geometry covering all points within a given distance from the input geometry.
- ST_AsText(geometry): Returns the Well-Known Text (WKT) representation of the geometry.

Below are example pairs of natural-language questions (NLQs) and their corresponding SQL queries:

"""

            # Build examples section
            examples_text = ""
            for i, ex in enumerate(similar_examples, 1):
                examples_text += f"[Example-{i}]\n"
                examples_text += f"NLQ: {ex['query']}\n"
                examples_text += f"SQL: {ex['sql']}\n\n"

            # Build prompt second half with schema
            prompt_second_half = """
Below is the database schema:

CREATE TABLE counties (
    "geometry" geometry(GEOMETRY,4326),
    "statefp" INTEGER,
    "countyfp" INTEGER,
    "countyns" BIGINT,
    "geoid" BIGINT,
    "name" TEXT,
    "namelsad" TEXT,
    "lsad" INTEGER,
    "classfp" TEXT,
    "mtfcc" TEXT,
    "csafp" TEXT,
    "cbsafp" TEXT,
    "metdivfp" TEXT,
    "funcstat" TEXT,
    "aland" BIGINT,
    "awater" BIGINT,
    "intptlat" DOUBLE PRECISION,
    "intptlon" DOUBLE PRECISION,
    "state" TEXT,
    "stateaabrv" TEXT
);

Description of table columns:

geometry - polygon for each county
statefp - state FIPS code
countyfp - county FIPS code
countyns - county GNIS/ANSI code
geoid - combined state+county FIPS
name - county name
namelsad - full county name including legal/statistical descriptor
lsad - legal/statistical area descriptor code
classfp - county class code
mtfcc - MAF/TIGER feature class code
csafp - central statistical area FIPS code
cbsafp - core-based statistical area FIPS code
metdivfp - metropolitan division FIPS code
funcstat - functional status of county (active/inactive)
aland - land area in square meters
awater - water area in square meters
intptlat - internal point latitude (centroid)
intptlon - internal point longitude (centroid)
state - full state name
stateaabrv - state two-letter abbreviation



Answer the following with no explanation:

NLQ: """

            # Build complete prompt
            prompt = prompt_first_half + examples_text + prompt_second_half + nl_query
            # Save for external use
            self.last_prompt = prompt

            # LOG THE PROMPT TO CONSOLE
            print("\n" + "="*80)
            print("PROMPT SENT TO REMOTE LLM:")
            print("="*80)
            print(prompt)
            print("="*80 + "\n")

            sql_text = None
            print(self.remote_llm_url)
            if not self.remote_llm_url:
                raise RuntimeError("LLM_API_URL not configured")
            # Call custom remote API expecting {"prompt": prompt} -> {"received"|"response"|"text": sql}
            resp = requests.post(self.remote_llm_url, json={"prompt": prompt}, timeout=45)
            resp.raise_for_status()
            payload = resp.json()
            sql_text = (payload.get("received") or payload.get("response") or payload.get("text") or "").strip()

            # LOG THE RESPONSE
            print("REMOTE LLM RESPONSE:")
            print("-"*80)
            print(f"Raw payload: {payload}")
            print(f"Extracted SQL: {sql_text}")
            print("-"*80 + "\n")

            if not sql_text:
                print("WARNING: Empty SQL returned from LLM")
                return None

            # Clean up - remove any markdown fences and NLQ: prefix if LLM echoed it
            sql_text = sql_text.replace("```sql", "").replace("```", "").strip()
            # Remove any "NLQ:" or "SQL:" prefixes that might have leaked through
            if sql_text.startswith("NLQ:"):
                sql_text = sql_text[4:].strip()
            if sql_text.startswith("SQL:"):
                sql_text = sql_text[4:].strip()
            sql_text = sql_text.rstrip(';')

            # Validate it looks like SQL
            if not sql_text.upper().startswith("SELECT"):
                print(f"WARNING: Response doesn't look like SQL: {sql_text[:100]}")
                return None

            return sql_text
        except Exception as e:
            print(f"Error in _refine_with_remote_llm: {e}")
            return None
