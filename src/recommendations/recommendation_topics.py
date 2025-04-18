import re
import time
import random
from typing import List, Dict, Any
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from recommendations.web_search import search_web

def is_valid_url(url):
    if not url.startswith(('http://', 'https://')):
        return False
    if re.search(r'[^\w\-\.\/\?\=\&\%\:\@]', url):
        return False
    blacklist = ['login', 'signin', 'account', '404', 'error', 'not-found']
    return not any(term in url.lower() for term in blacklist)

def generate_recommendations(topic: str, recommendation_chain=None, model=None) -> str:
    try:
        print("- Searching the web for related topics...")
        search_queries = [
            topic,
            f"{topic} guide",
            f"{topic} tutorial",
            f"{topic} overview",
            f"introduction to {topic}",
            f"{topic} research"
        ]
        
        all_results = []
        for query in search_queries:
            time.sleep(0.5)
            results = search_web(query, num_results=5)
            all_results.extend(results)
            if len(all_results) >= 15:
                break
                
        unique_results = []
        seen_urls = set()
        for result in all_results:
            url = result['url']
            if url not in seen_urls and is_valid_url(url):
                seen_urls.add(url)
                unique_results.append(result)
        
        prioritized_results = []
        other_results = []
        good_domains = ['.edu', '.gov', '.org', 'wikipedia.org', 'scholar.google', 'researchgate',
                      'springer.com', 'nature.com', 'sciencedirect.com', 'acm.org', 'ieee.org']
                      
        for result in unique_results:
            url = result['url']
            if any(domain in url for domain in good_domains):
                prioritized_results.append(result)
            else:
                other_results.append(result)
                
        search_results = prioritized_results + other_results
        
        formatted_recommendations = "# Related Topics You May Be Interested In\n\n"
        used_topics = set()
        count = 0
        
        for result in search_results:
            if count >= 5:
                break
            title = result['title']
            url = result['url']
            topic_name = re.sub(r'\s*[\|\-\–]\s*.*$', '', title)
            topic_name = re.sub(r'\s{2,}', ' ', topic_name).strip()
            if len(topic_name) < 5 or len(topic_name) > 70:
                continue
            if topic_name.lower() == topic.lower():
                continue
            similar = False
            for used_topic in used_topics:
                if (topic_name.lower() in used_topic.lower() or 
                    used_topic.lower() in topic_name.lower()):
                    similar = True
                    break
            
            if similar:
                continue
                
            description_prompt = ChatPromptTemplate.from_template(
                """
                I have a topic "{original_topic}" and a related topic "{related_topic}".
                In one or two sentences, explain why someone interested in "{original_topic}" 
                would also be interested in "{related_topic}". Be specific about the connection.
                Keep your response under 150 characters.
                """
            )
            description_chain = description_prompt | model | StrOutputParser()
            try:
                description = description_chain.invoke({
                    "original_topic": topic,
                    "related_topic": topic_name
                })
            except:
                description = f"This topic extends your knowledge of {topic} with additional perspectives."
            
            used_topics.add(topic_name)
            count += 1
            
            formatted_recommendations += f"## {count}. {topic_name}\n"
            formatted_recommendations += f"{description}\n"
            formatted_recommendations += f"[Learn more]({url})\n\n"
        
        if count < 5:
            backup_prompt = ChatPromptTemplate.from_template(
                f"""
                I'm creating a research report on "{topic}" and need {5 - count} more related topics
                that would be valuable for someone studying this area.
                
                I already have these topics: {", ".join(used_topics)}
                
                For each additional topic:
                1. Provide a specific, focused topic name related to {topic} (not something generic)
                2. Write a brief description explaining the specific connection to {topic}
                3. Include a URL to a real, reputable source like Wikipedia, a university site, 
                   or a well-known organization in this field where someone can learn about this topic
                
                Format each as:
                TOPIC: [topic name]
                DESCRIPTION: [description]
                URL: [url]
                """
            )
            backup_chain = backup_prompt | model | StrOutputParser()
            additional_recs = backup_chain.invoke({})
            
            current_rec = {"topic": "", "description": "", "url": ""}
            for line in additional_recs.split("\n"):
                line = line.strip()
                if not line:
                    continue
                    
                if line.upper().startswith("TOPIC:"):
                    if current_rec["topic"] and current_rec["url"]:
                        count += 1
                        formatted_recommendations += f"## {count}. {current_rec['topic']}\n"
                        formatted_recommendations += f"{current_rec['description']}\n"
                        formatted_recommendations += f"[Learn more]({current_rec['url']})\n\n"
                        
                        if count >= 5:
                            break
                    
                    current_rec = {"topic": "", "description": "", "url": ""}
                    current_rec["topic"] = line[6:].strip()
                    
                elif line.upper().startswith("DESCRIPTION:"):
                    current_rec["description"] = line[12:].strip()
                    
                elif line.upper().startswith("URL:"):
                    current_rec["url"] = line[4:].strip()
            
            if count < 5 and current_rec["topic"] and current_rec["url"]:
                count += 1
                formatted_recommendations += f"## {count}. {current_rec['topic']}\n"
                formatted_recommendations += f"{current_rec['description']}\n"
                formatted_recommendations += f"[Learn more]({current_rec['url']})\n\n"
        
        return formatted_recommendations
    
    except Exception as e:
        print(f"Error in web-based recommendations: {str(e)}")
        backup_prompt = ChatPromptTemplate.from_template(
            """
            I need to generate 5 related research topics for "{topic}" with reliable links.

            For each topic:
            1. Provide a specific, research-worthy topic name related to {topic}
            2. Write a brief description (1-2 sentences) of how it relates to {topic}
            3. Provide a link to one of these reliable sources (choose the most appropriate):
               - Wikipedia: https://en.wikipedia.org/wiki/[topic_name_with_underscores]
               - MIT OpenCourseWare: https://ocw.mit.edu/search/?q=[topic_name]
               - Khan Academy: https://www.khanacademy.org/search?referer=%2F&page_search_query=[topic_name]
               - arXiv: https://arxiv.org/search/?query=[topic_name]&searchtype=all
               - Science.gov: https://www.science.gov/scigov/desktop/en/results.html?query=[topic_name]

            Replace [topic_name] or [topic_name_with_underscores] with URL-friendly versions of the actual topic name.
            
            Format the output in markdown with clear headings and properly formatted links.
            """
        )
        backup_chain = backup_prompt | model | StrOutputParser()
        return backup_chain.invoke({"topic": topic})