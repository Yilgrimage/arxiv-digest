#!/usr/bin/env bash
# scripts/query_arxiv.sh — low-level arXiv API query
QUERY=$(printf '%s' "$1" | sed 's/ /+/g')
COUNT=${2:-5}
curl -sL "https://export.arxiv.org/api/query?search_query=all:${QUERY}&start=0&max_results=${COUNT}&sortBy=submittedDate&sortOrder=descending"
