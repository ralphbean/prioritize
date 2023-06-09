#!/usr/bin/env python3
""" Automatically prioritize features of one parent above others

Problem: If you use parent links to track different categories of features and you want to prioritize all
features of one parent above others (treat it as the focus), you have to manually comb through the
backlog and move the features up (increase their rank) for each one. If features under that parent have
different priority-field settings, you don't want to move them all to the top; you just want to move
them above other features of the same priority field setting. What a pain!

This script attempts to automate that for you.

This script accepts two arguments: a parent and a project. All of the features under that parent, in that
project will be prioritized up higher than the highest ranked feature for each priority-field tier.
(e.g., all Blocker features under the parent will be ranked above all other Blocker features. All
Critical features under the parent will be ranked above all other Critical features. All Major features
etc..)

"""

import argparse
import os
import sys

import click
import jira

PRIORITY = [
    "Undefined",
    "Minor",
    "Normal",
    "Major",
    "Critical",
    "Blocker",
]

DRY_RUN = False


@click.command(
    help=__doc__,
)
@click.option(
    "--dry-run",
    help="Do not update issues.",
    is_flag=True,
)
@click.option(
    "-p",
    "--parent",
    help="Parent we are prioritizing",
    required=True,
)
@click.option(
    "-p",
    "--project-id",
    help="Project that we are prioritizing in",
    required=True,
)
@click.option(
    "-t",
    "--token",
    help="JIRA personal access token",
    default=os.environ.get("JIRA_TOKEN"),
    required=True,
)
@click.option(
    "-u",
    "--url",
    help="JIRA URL",
    default=os.environ.get("JIRA_URL", "https://issues.redhat.com"),
)
def main(dry_run: bool, parent: str, project_id: str, token: str, url: str) -> None:
    global DRY_RUN
    DRY_RUN = dry_run
    jira_client = jira.client.JIRA(server=url, token_auth=token)

    all_fields = jira_client.fields()
    jira_name_map = {field["name"]: field["id"] for field in all_fields}
    rank_key = jira_name_map["Rank"]

    config = {
        "issues": ["Feature"],
        "rank_key": rank_key,
    }

    for issue_type in config["issues"]:
        process_type(jira_client, parent, project_id, issue_type, config)
    print("Done.")


def process_type(
    jira_client: jira.client.JIRA,
    parent: str,
    project_id: str,
    issue_type: str,
    config: dict,
) -> None:
    print(f"\n\n## Processing {issue_type}")

    priorities = PRIORITY
    issues = get_issues(jira_client, parent, project_id, issue_type)
    top_issues = get_highest_ranked_issues(
        jira_client, priorities, project_id, issue_type
    )

    for issue in issues:
        print(f"### {issue.key}")
        context = {
            "updates": [],
            "jira_client": jira_client,
            "rank_key": config["rank_key"],
        }
        check_rank(issue, context, top_issues)
        add_comment(issue, context)


def get_highest_ranked_issues(
    jira_client: jira.client.JIRA,
    priorities: list[str],
    project_id: str,
    issue_type: str,
) -> dict:
    """Return a dict of the highest ranked issues with each priority"""
    results = {}
    for priority in priorities:
        query = f"priority<={priority} AND project={project_id} AND type={issue_type} ORDER BY Rank ASC"
        issues = jira_client.search_issues(query, maxResults=1)
        if not issues:
            print(f"No {issue_type} found via query: {query}")
            sys.exit(1)
        results[priority] = issues[0]
    return results


def get_issues(
    jira_client: jira.client.JIRA, parent: str, project_id: str, issue_type: str
) -> list[jira.resources.Issue]:
    query = f'"Parent Link"={parent} AND project={project_id} AND type={issue_type} ORDER BY Rank DESC'
    print("  ?", query)
    results = jira_client.search_issues(query, maxResults=0)
    if not results:
        print(f"No {issue_type} found via query: {query}")
        sys.exit(1)
    print("  =", f"{len(results)} results:", [r.key for r in results])
    return results


def check_rank(issue: jira.resources.Issue, context: dict, top_issues: dict) -> None:
    priority = issue.fields.priority.name
    top_issue = top_issues[priority]
    top_issues[priority] = issue
    context["updates"].append(
        f"  > Issue rank of {issue.key}({priority}) moved above {top_issue.key}"
    )
    if not DRY_RUN:
        context["jira_client"].rank(issue.key, next_issue=top_issue.key)


def add_comment(issue: jira.resources.Issue, context: dict):
    if context["updates"]:
        print("\n".join(context["updates"]))


if __name__ == "__main__":
    main()
