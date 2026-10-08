"""Poll read models and web vote policy; HTTP rendering stays in the blueprint."""
import json
import sqlite3

from app.repositories.member_repo import MemberRepository
from app.repositories.poll_repo import PollRepository
from app.services import poll_service


def _options(raw):
    try:
        return json.loads(raw or '[]')
    except (TypeError, json.JSONDecodeError):
        return []


def vote_on_page(connection, *, poll_id, member_id, clear_vote, option_indexes,
                 single_index, logger):
    if poll_id is None:
        return 'Invalid vote', 'error'
    try:
        poll = PollRepository(connection).get_by_id(poll_id)
    except sqlite3.Error as exc:
        logger.warning('polls_page_failure reason_code=poll_lookup_failed poll_id=%s error=%s', poll_id, exc)
        return 'Polls are temporarily unavailable', 'error'
    if poll is None:
        return None
    options = _options(poll['options_json'])
    multiple = bool(poll['allow_multiple'])
    if poll['status'] != 'open':
        return 'Poll is closed', 'error'
    if not options:
        return 'Poll has invalid options', 'error'
    if clear_vote:
        if not multiple:
            return 'Invalid vote', 'error'
        poll_service.clear_poll_votes(connection, poll_id, member_id)
        return 'Your votes were cleared', 'success'
    raw_indexes = option_indexes if multiple else ([] if single_index is None else [str(single_index)])
    try:
        indexes = [int(v) for v in raw_indexes]
    except ValueError:
        indexes = None
    if not indexes or any(i < 0 or i >= len(options) for i in indexes):
        return 'Invalid poll option', 'error'
    if multiple:
        # Form resubmission adds selections; only explicit clear removes them.
        for index in indexes:
            poll_service.record_poll_vote_additive(connection, poll_id, member_id, index)
    else:
        poll_service.record_poll_vote(connection, poll_id, member_id, indexes[0], False)
    return 'Poll vote recorded!', 'success'


def build_poll_page(connection, *, member_id, logger):
    repo = PollRepository(connection)
    messages = []
    try:
        rows = repo.list_for_page()
    except sqlite3.Error as exc:
        rows = []
        logger.warning('polls_page_failure reason_code=poll_list_failed error=%s', exc)
        messages.append(('Polls are temporarily unavailable', 'error'))
    member = MemberRepository(connection).get_by_id(member_id)
    linked = bool(member and (member['telegram_username'] or member['telegram_user_id'] is not None))
    polls = []
    for row in rows:
        poll = dict(row)
        options = _options(poll['options_json'])
        try:
            votes = [dict(v) for v in repo.votes_for_page(poll['id'])]
            own_rows = repo.member_votes(poll['id'], member_id)
        except sqlite3.Error as exc:
            votes, own_rows = [], []
            logger.warning('polls_page_failure reason_code=poll_votes_load_failed poll_id=%s error=%s', poll['id'], exc)
        counts = [0] * len(options)
        for vote in votes:
            if vote['option_index'] < len(counts):
                counts[vote['option_index']] += 1
        poll.update(options=options, votes=votes, counts=counts, allow_multiple=bool(poll['allow_multiple']),
                    user_votes=[v['option_index'] for v in own_rows])
        if poll['allow_multiple']:
            try:
                poll['total_voters'] = repo.voter_count(poll['id'])
            except sqlite3.Error:
                poll['total_voters'] = sum(counts)
        else:
            poll['total_voters'] = sum(counts)
        polls.append(poll)
    return {'polls': polls, 'is_telegram_linked': linked}, messages


def list_api_polls(connection, limit, offset):
    polls = []
    for row in PollRepository(connection).list_for_api(limit, offset):
        poll = dict(row)
        poll['options'] = _options(poll.pop('options_json'))
        poll['allow_multiple'] = bool(poll['allow_multiple'])
        polls.append(poll)
    return polls
