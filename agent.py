from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict
import anthropic
import httpx
import json
import os

app = FastAPI(title="Genomica", description="AI-powered genomic variant interpretation and pharmacogenomics agent")
client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

class VariantQuery(BaseModel):
  gene: str
  variant: str
  rsid: Optional[str] = None
  patient_phenotype: Optional[str] = None

class VariantInterpretation(BaseModel):
  gene: str
  variant: str
  pathogenicity: str
  clinical_significance: str
  associated_conditions: List[str]
  functional_impact: str
  population_frequency: Optional[float]
  therapeutic_implications: List[str]
  evidence_sources: List[str]
  confidence: float

class PharmacoQuery(BaseModel):
  gene: str
  drug: str
  variants: Optional[List[str]] = None

class PharmacoResult(BaseModel):
  gene: str
  drug: str
  interaction_type: str
  phenotype: str
  dosage_recommendation: str
  alternative_drugs: List[str]
  evidence_level: str
  cpic_guideline: Optional[str]

class GenomeQuery(BaseModel):
  condition: str
  inheritance_pattern: Optional[str] = None
  population: Optional[str] = None

class GeneList(BaseModel):
  condition: str
  genes: List[Dict[str, str]]
  inheritance_patterns: List[str]
  prevalence: str
  screening_recommendations: str

VARIANT_CLASSIFICATIONS = {
  "pathogenic": "Causes disease, strong evidence",
  "likely_pathogenic": "Probably causes disease, moderate evidence",
  "uncertain_significance": "VUS - unclear clinical impact",
  "likely_benign": "Probably not disease-causing",
  "benign": "Not disease-causing"
}

PHARMACO_GENES = [
  "CYP2D6", "CYP2C19", "CYP2C9", "CYP3A4", "CYP3A5",
  "DPYD", "TPMT", "UGT1A1", "SLCO1B1", "VKORC1",
  "CFTR", "BRCA1", "BRCA2", "EGFR", "KRAS"
]

async def query_ensembl(gene: str, variant: str) -> dict:
  async with httpx.AsyncClient() as hclient:
    try:
      url = f"https://rest.ensembl.org/vep/human/hgvs/{gene}:{variant}"
      headers = {"Content-Type": "application/json", "Accept": "application/json"}
      r = await hclient.get(url, headers=headers, timeout=10)
      if r.status_code == 200:
        data = r.json()
        if data:
          return data[0]
      return {"gene": gene, "variant": variant, "status": "not found in Ensembl"}
    except:
      return {"gene": gene, "variant": variant, "status": "Ensembl unavailable"}

async def query_clinvar(rsid: str) -> dict:
  async with httpx.AsyncClient() as hclient:
    try:
      if not rsid:
        return {}
      url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
      params = {"db": "clinvar", "term": rsid, "retmode": "json", "retmax": 1}
      r = await hclient.get(url, params=params, timeout=10)
      data = r.json()
      ids = data.get("esearchresult", {}).get("idlist", [])
      return {"clinvar_ids": ids, "rsid": rsid, "url": f"https://www.ncbi.nlm.nih.gov/clinvar/?term={rsid}"}
    except:
      return {"rsid": rsid, "status": "ClinVar unavailable"}

async def query_pharmgkb(gene: str, drug: str) -> dict:
  async with httpx.AsyncClient() as hclient:
    try:
      url = f"https://api.pharmgkb.org/v1/data/clinicalAnnotation"
      params = {"view": "base", "geneSymbol": gene, "drug": drug}
      r = await hclient.get(url, params=params, timeout=10)
      if r.status_code == 200:
        return r.json()
      return {"gene": gene, "drug": drug, "status": "no data"}
    except:
      return {"gene": gene, "drug": drug, "status": "PharmGKB unavailable"}

@app.post("/interpret-variant", response_model=VariantInterpretation)
async def interpret_variant(query: VariantQuery):
  ensembl_data = await query_ensembl(query.gene, query.variant)
  clinvar_data = await query_clinvar(query.rsid or "")

  prompt = f"""You are a clinical genomics AI agent interpreting genetic variants.

Gene: {query.gene}
Variant: {query.variant}
RSID: {query.rsid or 'not provided'}
Patient Phenotype: {query.patient_phenotype or 'not provided'}
Ensembl VEP Data: {ensembl_data}
ClinVar Data: {clinvar_data}
Classification System: {VARIANT_CLASSIFICATIONS}

Provide clinical variant interpretation as JSON:
{{
  "pathogenicity": "pathogenic/likely_pathogenic/uncertain_significance/likely_benign/benign",
  "clinical_significance": "clinical meaning",
  "associated_conditions": ["condition1"],
  "functional_impact": "protein/RNA impact",
  "population_frequency": 0.0,
  "therapeutic_implications": ["implication1"],
  "evidence_sources": ["source1"],
  "confidence": 0.0
}}"""

  response = client.messages.create(
    model="claude-opus-4-5",
    max_tokens=1200,
    messages=[{"role": "user", "content": prompt}]
  )
  text = response.content[0].text
  start = text.find("{")
  end = text.rfind("}") + 1
  try:
    result = json.loads(text[start:end])
  except json.JSONDecodeError:
    result = {"pathogenicity": "uncertain_significance", "clinical_significance": text, "associated_conditions": [], "functional_impact": "unknown", "population_frequency": None, "therapeutic_implications": [], "evidence_sources": [], "confidence": 0.3}

  return VariantInterpretation(gene=query.gene, variant=query.variant, **result)

@app.post("/pharmacogenomics", response_model=PharmacoResult)
async def analyze_pharmacogenomics(query: PharmacoQuery):
  pharmgkb_data = await query_pharmgkb(query.gene, query.drug)

  prompt = f"""You are a pharmacogenomics AI agent analyzing drug-gene interactions.

Gene: {query.gene}
Drug: {query.drug}
Variants: {query.variants or 'standard'}
PharmGKB Data: {pharmgkb_data}

Provide pharmacogenomics analysis as JSON:
{{"interaction_type": "metabolism/efficacy/toxicity/dosage", "phenotype": "poor/intermediate/normal/ultrarapid metabolizer", "dosage_recommendation": "specific recommendation", "alternative_drugs": ["drug1"], "evidence_level": "1A/1B/2A/2B/3/4", "cpic_guideline": "guideline URL or null"}}"""

  response = client.messages.create(
    model="claude-opus-4-5",
    max_tokens=800,
    messages=[{"role": "user", "content": prompt}]
  )
  text = response.content[0].text
  start = text.find("{")
  end = text.rfind("}") + 1
  try:
    result = json.loads(text[start:end])
  except json.JSONDecodeError:
    result = {"interaction_type": "metabolism", "phenotype": "normal metabolizer", "dosage_recommendation": text, "alternative_drugs": [], "evidence_level": "3", "cpic_guideline": None}

  return PharmacoResult(gene=query.gene, drug=query.drug, **result)

@app.post("/disease-genes", response_model=GeneList)
async def get_disease_genes(query: GenomeQuery):
  prompt = f"""You are a medical genetics AI agent with comprehensive knowledge of disease-gene associations.

Condition: {query.condition}
Inheritance Pattern: {query.inheritance_pattern or 'any'}
Population: {query.population or 'general'}

List the key genes associated with this condition as JSON:
{{"genes": [{{"gene": "GENE1", "role": "primary/modifier", "frequency": "common/rare"}}], "inheritance_patterns": ["AD", "AR"], "prevalence": "1 in X", "screening_recommendations": "recommendations"}}"""

  response = client.messages.create(
    model="claude-opus-4-5",
    max_tokens=900,
    messages=[{"role": "user", "content": prompt}]
  )
  text = response.content[0].text
  start = text.find("{")
  end = text.rfind("}") + 1
  try:
    result = json.loads(text[start:end])
  except json.JSONDecodeError:
    result = {"genes": [], "inheritance_patterns": [], "prevalence": "unknown", "screening_recommendations": text}

  return GeneList(condition=query.condition, **result)

@app.get("/pharmaco-genes")
def get_pharmaco_genes():
  return {"genes": PHARMACO_GENES, "note": "Key pharmacogenomics genes with clinical actionability"}

@app.get("/health")
def health():
  return {"status": "ok", "service": "genomica"}

if __name__ == "__main__":
  import uvicorn
  uvicorn.run(app, host="0.0.0.0", port=8000)
