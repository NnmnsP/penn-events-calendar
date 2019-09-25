#!/usr/bin/python
import os
import re
import requests
import json
import time
import numpy as np
import pandas as pd
from unidecode import unidecode
from datetime import datetime, timedelta
import dateutil.parser
from itertools import chain
from lxml import etree, html
from bs4 import BeautifulSoup, NavigableString
from urllib.parse import urljoin
from tqdm import tqdm


PATH_DATA = os.path.join('data', 'events.json')  # path to save events
GROBID_URL = 'http://localhost:8070'
GROBID_PDF_URL = '{}/api/processFulltextDocument'.format(GROBID_URL)
PRODUCE_VECTOR = True  # if True, produce vector


if PRODUCE_VECTOR:
    PATH_VECTOR = os.path.join('data', 'events_vector.json')
    import string
    from nltk.stem.porter import PorterStemmer
    from nltk.tokenize import WhitespaceTokenizer
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.decomposition import TruncatedSVD
    from sklearn.neighbors import NearestNeighbors

    stemmer = PorterStemmer()
    w_tokenizer = WhitespaceTokenizer()
    punct_re = re.compile('[{}]'.format(re.escape(string.punctuation)))

    def preprocess(text, stemming=True):
        """
        Apply Snowball stemmer to string
        Parameters
        ----------
        text : str, input abstract of papers/posters string
        stemming : boolean, apply Porter stemmer if True,
            default True
        """
        text = text or ''
        text = unidecode(text).lower()
        text = punct_re.sub(' ', text)  # remove punctuation
        if stemming:
            words = w_tokenizer.tokenize(text)
            text_preprocess = ' '.join([stemmer.stem(word) for word in words])
        else:
            words = w_tokenizer.tokenize(text)
            text_preprocess = ' '.join([stemmer.stem(word) for word in words])
        return text_preprocess


PATTERNS = [
    r'^[a-zA-Z]+, ([a-zA-Z]+ [0-9]{1,2}, [0-9]{4}).*',
    r'^([a-zA-Z]+ [0-9]{1,2}, [0-9]{4}) .*',
    r'^([a-zA-Z]+ [0-9]{1,2}) @.*',
    r'^([a-zA-Z]{3}\.? [0-9]{1,2}, [0-9]{4}) .*',
    r'^([a-zA-Z]{3} [0-9]{1,2} [0-9]{4})[0-9]{1,2}:[0-9]{2}.*',
    r'^[a-zA-Z]{3}, ([0-9\/]{10}) .*',
    r'^[a-zA-Z]+, ([0-9]{1,2} [a-zA-Z]+ [0-9]{4})[— ]-?.*',
    r'^([0-9]{1,2} [a-zA-Z]{3} [0-9]{4}) .*'
]
PATS = [re.compile(pattern) for pattern in PATTERNS]


def clean_date_format(d):
    """
    Clean date in string
    e.g. 'Tuesday, October 30, 2018 - 11:30am', '02/06/2019', '1.3.18'
    to string in 'DD-MM-YYYY' format
    """
    try:
        return dateutil.parser.parse(d).strftime('%d-%m-%Y')
    except:
        d = d.replace('Date TBD', '')
        d = d.replace('EDT', '').replace('Special time:', '')
        d = d.replace('Wu & Chen Auditorium', '')
        d = d.replace('-', '')
        d = d.replace('\n', ' ')
        d = re.sub(r'(\d+\:\d+\s?(?:AM|PM|am|pm|A.M.|P.M.|a.m.|p.m.))', '', d)
        d = d.replace('-', '').strip()
        if d is not '':
            for pat in PATS:
                if pat.match(d):
                    d = pat.sub(r"\1", d)
                    return dateutil.parser.parse(d).strftime('%d-%m-%Y')
            return dateutil.parser.parse(d).strftime('%d-%m-%Y')
        else:
            return ''


def clean_starttime(r):
    if '-' in r['starttime']:
        starttime = r['starttime'].split('-')[0].strip()
    else:
        starttime = r['starttime']
    return starttime


def clean_endtime(r):
    if '-' in r['starttime']:
        endtime = r['starttime'].split('-')[-1].strip()
    else:
        try:
            endtime = dateutil.parser.parse(r['starttime']) + timedelta(hours=1)
            endtime = endtime.strftime("%I:%M %p")
        except:
            endtime = r['endtime']
    return endtime


def find_startend_time(s):
    """
    Find starttime and endtime from a given string
    """
    starttime, endtime = '', ''
    ts = re.findall(r'(\d+\:\d+\s?(?:AM|PM|am|pm|A.M.|P.M.|a.m.|p.m.))', s)
    if len(ts) == 1:
        starttime = ts[0]
        endtime = ''
    elif len(ts) == 2:
        starttime = ts[0]
        endtime = ts[1]
    return starttime, endtime


def read_json(file_path):
    """
    Read collected file from path
    """
    if not os.path.exists(file_path):
        events = []
        return events
    else:
        with open(file_path, 'r') as fp:
            events = [json.loads(line) for line in fp]
        return events


def save_json(ls, file_path):
    """
    Save list of dictionary to JSON
    """
    with open(file_path, 'w') as fp:
        fp.write('[\n  ' + ',\n  '.join(json.dumps(i) for i in ls) + '\n]')


def convert_event_to_dict(event):
    """
    Convert event XML to dictionary
    """
    event_dict = {}
    keys = [
        'date', 'starttime', 'endtime',
        'title', 'description', 'location',
        'room', 'url', 'student', 'privacy',
        'category', 'school', 'owner',
    ]
    for key in keys:
        value = event.find(key).text or ''
        if key == 'description':
            value = BeautifulSoup(value, 'html.parser').text  # description
        elif key in ('starttime', 'endtime'):
            value = datetime.strptime(value, "%H:%M:%S").strftime("%I:%M %p")
        elif key == 'url':
            if len(value) > 0:
                event_dict['event_id'] = str(int(value.rsplit('/')[-1]))
            else:
                event_dict['event_id'] = ''
        else:
            value = unidecode(value)
        event_dict[key] = value
    return event_dict


def fetch_events():
    """
    Saving Penn events to JSON format
    """
    base_url = 'http://www.upenn.edu/calendar-export/?showndays=50'
    page = requests.get(base_url)
    tree = html.fromstring(page.content)
    events = tree.findall('event')

    events_list = []
    for event in events:
        try:
            event_dict = convert_event_to_dict(event)
            events_list.append(event_dict)
        except:
            pass
    return events_list


def stringify_children(node):
    """
    Filters and removes possible Nones in texts and tails
    ref: http://stackoverflow.com/questions/4624062/get-all-text-inside-a-tag-in-lxml
    """
    parts = ([node.text] +
             list(chain(*([c.text, c.tail] for c in node.getchildren()))) +
             [node.tail])
    return ''.join(filter(None, parts))


def fetch_events_cni(base_url='https://cni.upenn.edu/events'):
    """
    Fetch events from Computational Neuroscience Initiative (CNI)
    """
    page = requests.get(base_url)
    event_page = BeautifulSoup(page.content, 'html.parser')
    all_events = event_page.find_all('ul', attrs={'class': 'unstyled'})[1]

    events = []
    all_events = all_events.find_all('li')
    for event in all_events:
        event_id = event.find('a').attrs.get('href', '')
        event_url = urljoin(base_url, event_id)
        date = event.find('span', attrs={'class': 'date-display-single'})
        if date is not None:
            date, event_time = date.attrs.get('content').split('T')
            if '-' in event_time:
                starttime = event_time.split('-')[0]
                starttime = dateutil.parser.parse(starttime)
                endtime = (starttime + timedelta(hours=1))
                starttime, endtime = starttime.strftime("%I:%M %p"), endtime.strftime("%I:%M %p")
            else:
                starttime, endtime = '', ''
        else:
            date, starttime, endtime = '', '', ''

        location = event.find('div', attrs={'class': 'location'})
        location = location.get_text().strip() if location is not None else ''
        title = event.find('a')
        title = title.text if title is not None else ''
        speaker = event.find('a')
        speaker = speaker.text.split(':')[-1] if ':' in speaker.text else ''

        try:
            event_page = requests.get(event_url)
            event_soup = BeautifulSoup(event_page.content, 'html.parser')
            description = []
            description_soup = event_soup.find_all('div', attrs={'class': 'field-item even'})
            for div in description_soup:
                if div.find('strong') is None:
                    description.append(div.text)
                else:
                    description.append('\n'.join([d.text for d in div.find_all('strong')] + [p.text for p in div.find_all('p')]))
            description = ' '.join(description)
        except:
            description = ''

        events.append({
            'title': title,
            'date': date,
            'location': location,
            'description': description,
            'starttime': starttime,
            'endtime': endtime,
            'url': event_url,
            'speaker': speaker,
            'owner': 'Computational Neuroscience Initiative (CNI)'
        })
    return events


def fetch_events_english_dept(base_url='https://www.english.upenn.edu/events/calendar-export/'):
    """
    Saving English Department events to JSON format
    """
    events_list = []
    page = requests.get(base_url)
    site = html.fromstring(page.text)
    events = site.xpath(
        '//ul[@class="unstyled"]//li//span[@class="field-content"]')
    events = events[0]
    event_months = [stringify_children(e).strip(
    ) for e in events.xpath('//div[@class="month-date"]')]
    event_days = [stringify_children(e).strip()
                  for e in events.xpath('//div[@class="day-date"]')]
    event_locations = events.xpath('//p[@class="location"]/text()')

    starttimes = []
    endtimes = []
    for div in events.xpath('//div[@class="date-time"]'):
        event_time = div.find('span[@class="date-display-single"]')
        if event_time is not None and event_time.find('span[@class="date-display-start"]') is not None:
            starttime = event_time.find(
                'span[@class="date-display-start"]').text
            endtime = event_time.find('span[@class="date-display-end"]').text
            starttimes.append(starttime)
            endtimes.append(endtime)
        else:
            starttimes.append(event_time.text or '')
            endtimes.append(event_time.text or '')

    titles = [span.find('a').text for span in events.xpath('//span[@class="field-content"]')
              if span.find('a') is not None]
    urls = [span.find('a').attrib.get('href') for span in events.xpath('//span[@class="field-content"]')
            if span.find('a') is not None]
    descriptions = [stringify_children(e).strip()
                    for e in events.xpath('//div[@class="span10"]')]

    for (month, day, location, starttime, endtime, title, description, url) in zip(event_months, event_days, event_locations, starttimes, endtimes, titles, descriptions, urls):
        try:
            date = '{} {}'.format(day, month)
            date = re.sub(r'to \d+', '', date)
            event_dict = {
                "date": dateutil.parser.parse(date).strftime("%Y-%m-%d"),
                "starttime": starttime,
                "endtime": endtime,
                "title": title,
                "description": description,
                "location": location,
                "speaker": '',
                "url": urljoin(base_url, url),
                "owner": "English Department",
            }
            events_list.append(event_dict)
        except:
            pass
    return events_list


def fetch_events_crim(base_url='https://crim.sas.upenn.edu'):
    """
    Fetch events from Department of Criminology (CRIM)
    """
    events = []
    page = requests.get(base_url + '/events')
    soup = BeautifulSoup(page.content, 'html.parser')
    events_soup = soup.find(
        'div', attrs={'class': 'item-list'}).find('ul', attrs={'class': 'unstyled'})
    if events_soup is not None:
        for a in events_soup.find_all('a'):
            event_path = a.get('href')
            event_url = base_url + event_path
            event_page = requests.get(event_url)
            soup = BeautifulSoup(event_page.content, 'html.parser')
            title = soup.find('div', attrs={'class': 'span-inner-wrapper'}).\
                find('h1', attrs={'class': 'page-header'}).text
            date = soup.find(
                'div', attrs={'class': 'field-date'}).find('span').text
            location = soup.find('div', attrs={'class': 'field-location'})
            location = location.find('p').text or ''
            description = soup.find('div', attrs={'class': 'field-body'})
            description = description.find(
                'p').text if description is not None else ''
            try:
                dt = dateutil.parser.parse(date)
                starttime = dt.strftime('%I:%M %p')
                endtime = (dt + timedelta(hours=1)).strftime('%I:%M %p')
            except:
                starttime = ''
                endtime = ''
            events.append({
                'title': title,
                'date': date,
                'starttime': starttime,
                'location': location,
                'description': description,
                'url': event_url,
                'owner': 'Dapartment of Criminology',
                'endtime': endtime
            })
    return events


def fetch_events_mec(base_url='https://www.sas.upenn.edu'):
    """
    Fetch events from Middle East Center (MEC) https://www.sas.upenn.edu/mec/events
    """
    events = []
    page = requests.get(base_url + '/mec/events')
    soup = BeautifulSoup(page.content, 'html.parser')
    event_urls = soup.find_all(
        'div', attrs={'class': 'frontpage-calendar-link'})
    for div in event_urls:
        event_url = base_url + div.find('a')['href']
        event_page = requests.get(event_url)
        event_soup = BeautifulSoup(event_page.content, 'html.parser')
        event_details = event_soup.find('div', attrs={'class': 'node-inner'})
        date = event_details.find('div', attrs={'class': 'event_date'}).text
        title = event_details.find('div', attrs={'class': 'event_title'}).text
        try:
            description = (event_details.find(
                'div', attrs={'class': 'event_content'}).text or '').strip()
        except:
            pass
        try:
            dt = dateutil.parser.parse(date)
            starttime = dt.strftime('%I:%M %p')
            endtime = endtime = (dt + timedelta(hours=1)).strftime('%I:%M %p')
        except:
            starttime = ''
            endtime = ''
        events.append({
            'title': title,
            'date': date,
            'description': description,
            'owner': 'Middle East Center',
            'url': event_url,
            'location': '',
            'speaker': '',
            'starttime': starttime,
            'endtime': endtime
        })
    return events


def fetch_events_biology(base_url='http://www.bio.upenn.edu'):
    """
    Fetch events from Department of Biology http://www.bio.upenn.edu/events/
    """
    events = []
    page = requests.get(base_url + '/events')
    soup = BeautifulSoup(page.content, 'html.parser')

    for event in soup.find('div', attrs={'class': 'events-listing'}).find_all('summary', attrs={'class': 'col-md-11'}):
        event_url = base_url + event.find('a')['href']
        title = event.find('a')
        title = title.text if title is not None else ''
        event_time = event.find('span', attrs={'class': 'news-date'})
        event_time = event_time.text if event_time is not None else ''
        event_soup = BeautifulSoup(page.content, 'html.parser')
        date = event_soup.find('span', attrs={'class': 'date-display-single'})
        date = date.text if date is not None else ''
        location = event_soup.find(
            'div', attrs={'class': 'field field-type-text field-field-event-location'})
        location = location.find(
            'div', attrs={'class': 'field-item odd'}).text if location is not None else ''
        description = event_soup.find('div', attrs={'class': 'node-inner'})
        description = description.find('div', attrs={'class': 'content'}).find(
            'p').text if description is not None else ''
        events.append({
            'title': title,
            'date': date,
            'location': location,
            'description': description,
            'owner': 'Department of Biology',
            'url': event_url
        })
    return events


def fetch_events_economics(base_url='https://economics.sas.upenn.edu'):
    """
    Fetch events from Economics department https://economics.sas.upenn.edu/events

    Note that we still have problem with when parsing the description
    """
    events = []
    html_page = requests.get(base_url + '/events')
    soup = BeautifulSoup(html_page.content, 'html.parser')
    pagination = soup.find('nav', attrs={'class': 'pager-nav text-center'})
    n_pages = max([int(a['href'][-1]) for a in pagination.find_all('a')])

    # loop through all pages
    for page in range(n_pages + 1):
        all_event_url = 'https://economics.sas.upenn.edu/events?tid=All&page={}'.format(page)
        page = requests.get(all_event_url)
        all_event_soup = BeautifulSoup(page.content, 'html.parser')
        page_events = all_event_soup.find(
            'ul', attrs={'class': 'list-unstyled row'}).find_all('li')

        for event in page_events:
            event_url = base_url + event.find('a')['href']
            try:
                start_time, end_time = event.find_all('time')
                start_time = start_time.text.strip() if start_time is not None else ''
                start_time = start_time.split(' - ')[-1]
                date = start_time.split(' - ')[0]
                end_time = end_time.text.strip() if end_time is not None else ''
                end_time = end_time.split(' - ')[-1]
            except:
                start_time, end_time = '', ''
            event_page = requests.get(event_url)
            event_soup = BeautifulSoup(event_page.content, 'html.parser')
            title = event_soup.find('h1', attrs={'class': 'page-header'})
            title = title.text.strip() if title is not None else ''
            speaker = event_soup.find(
                'div', attrs={'class': 'col-sm-4 bs-region bs-region--right'})
            speaker = speaker.text.replace(
                'Download Paper', '').strip() if speaker is not None else ''

            try:
                pdf_path = event_soup.find(
                    'a', attrs={'class': 'btn btn-lg btn-primary btn-download'})['href']
                pdf_url = urljoin('https://economics.sas.upenn.edu/', pdf_path)
                parsed_article = requests.post(
                    GROBID_PDF_URL, files={'input': requests.get(pdf_url).content}).text
                pdf_soup = BeautifulSoup(parsed_article, 'lxml')
                title = pdf_soup.find('title')
                title = title.text if title is not None else ''
                description = pdf_soup.find('abstract')
                description = description.text.strip() if description is not None else ''
            except:
                description = ''

            location = event_soup.find(
                'p', attrs={'class': 'address'}).text.strip()
            events.append({
                'title': title,
                'description': description,
                'speaker': speaker,
                'date': date,
                'starttime': start_time,
                'endtime': end_time,
                'location': location,
                'url': event_url,
                'owner': 'Department of Economics'
            })
    return events


def fetch_events_math(base_url='https://www.math.upenn.edu'):
    """
    Fetch event from Math department
    """
    events = []
    html_page = requests.get(base_url + '/events')
    page_soup = BeautifulSoup(html_page.content, 'html.parser')
    pagination = page_soup.find(
        'div', attrs={'class': 'pagination pagination-centered'})

    n_pages = max([int(page.text)
                   for page in pagination.find_all('li') if page.text.isdigit()])

    for page in range(n_pages):
        all_event_url = 'https://www.math.upenn.edu/events/?page=%s' % str(
            page)
        all_event_page = requests.get(all_event_url)
        all_event_soup = BeautifulSoup(all_event_page.content, 'html.parser')

        event_urls = [base_url + header.find('a')['href'] for header in all_event_soup.find_all('h3')
                      if 'events' in header.find('a')['href']]

        for event_url in event_urls:
            event_page = requests.get(event_url)
            event_soup = BeautifulSoup(event_page.content, 'html.parser')
            try:
                event_detail_soup = event_soup.find(
                    'div', attrs={'class': "pull-right span9"})
                title = event_detail_soup.find(
                    'h3', attrs={'class': 'field-og-group-ref'}).find('a').text
                date = event_detail_soup.find(
                    'p', attrs={'class': 'field-date'}).text.strip()
                speaker = event_detail_soup.find(
                    'h4', attrs={'class': 'field-speaker-name'}).text.strip()
                speaker_affil = event_detail_soup.find(
                    'p', attrs={'class': 'field-speaker-affiliation'}).text.strip()
                location = event_detail_soup.find(
                    'div', attrs={'class': 'fieldset-wrapper'}).text.strip()
                description_soup = event_detail_soup.find(
                    'div', attrs={'class': 'field-body'})
                if description_soup is not None:
                    description = description_soup.text.strip()
                else:
                    description = ''
                events.append({
                    'title': title,
                    'date': date,
                    'speaker': speaker + ', ' + speaker_affil,
                    'location': location,
                    'description': description,
                    'url': event_url,
                    'owner': 'Math Department',
                    'starttime': date,
                    'endtime': ''
                })
            except:
                pass
    return events


def fetch_events_philosophy(base_url='https://philosophy.sas.upenn.edu'):
    """
    Fetch event from Philosophy (Penn Arts & Science) at https://philosophy.sas.upenn.edu
    """
    events = []
    html_page = requests.get(base_url + '/events')
    page_soup = BeautifulSoup(html_page.content, 'html.parser')
    events_list = page_soup.find(
        'div', attrs={'class': 'item-list'}).find_all('li')

    if len(events_list) > 0:
        for li in events_list:
            event_url = base_url + li.find('a')['href']
            title = li.find('h3').text.strip()
            date = li.find('p', attrs={'class': 'dateline'})
            date = date.text.strip() if date is not None else ''
            location = li.find('div', attrs={'class': 'location'})
            location = location.text.strip() if location is not None else ''

            event_page = requests.get(event_url)
            event_soup = BeautifulSoup(event_page.content, 'html.parser')
            event_time = event_soup.find('div', attrs={'class': 'field-date'})
            event_time = event_time.text.strip() if event_time is not None else ''
            starttime, endtime = find_startend_time(event_time)
            description = event_soup.find('div', attrs={'class': 'field-body'})
            description = description.text.strip() if description is not None else ''

            events.append({
                'title': title,
                'date': date,
                'location': location,
                'description': description,
                'url': event_url,
                'starttime': starttime,
                'endtime': endtime,
                'owner': 'Department of Philosophy'
            })
    return events


def fetch_events_classical_studies(base_url='https://www.classics.upenn.edu'):
    """
    Fetch events from Classical studies
    """
    events = []
    html_page = requests.get(base_url + '/events')
    page_soup = BeautifulSoup(html_page.content, 'html.parser')
    events_list = page_soup.find('div', attrs={'class': 'item-list'})

    for event_url in events_list.find_all('a'):
        event_url = base_url + event_url['href']
        event_page = requests.get(event_url)
        event_soup = BeautifulSoup(event_page.content, 'html.parser')
        if event_soup is not None:
            title = event_soup.find('h1', attrs={'class': 'page-header'})
            title = title.text if title is not None else ''
            date = event_soup.find(
                'span', attrs={'class': 'date-display-single'})
            date = date.text if date is not None else ''
            if event_soup.find('p', attrs={'class': 'MsoNormal'}) is not None:
                location = event_soup.find(
                    'p', attrs={'class': 'MsoNormal'}).text
            elif event_soup.find('p').text is not None:
                location = event_soup.find('p').text
            else:
                location = ''
            description = event_soup.find('div', attrs={
                                          'class': 'field field-name-body field-type-text-with-summary field-label-hidden'})
            if description is not None:
                description = description.text
            else:
                description = ''
            try:
                starttime = event_soup.find(
                    'span', attrs={'class': 'date-display-start'}).text.strip()
            except:
                startime = ''
            try:
                endtime = event_soup.find(
                    'span', attrs={'class': 'date-display-end'}).text.strip()
            except:
                endtime = ''
            events.append({
                'title': title,
                'date': date,
                'location': location,
                'description': description,
                'url': event_url,
                'starttime': starttime,
                'endtime': endtime,
                'owner': 'Department of Classical Studies'
            })
    return events


def fetch_events_linguistic(base_url='https://www.ling.upenn.edu'):
    """
    Fetch events from Linguistic Department
    """
    events = []
    html_page = requests.get(base_url + '/events')
    page_soup = BeautifulSoup(html_page.content, 'html.parser')
    for event in page_soup.find('div', attrs={'class': 'view-content'}).find_all('li'):
        if event.find('a') is not None:
            event_url = base_url + event.find('a')['href']
            event_page = requests.get(event_url)
            event_soup = BeautifulSoup(event_page.content, 'html.parser')
            title = event_soup.find(
                'h1', attrs={'class': 'title'}).text.strip()
            try:
                location = event.find(
                    'div', attrs={'class': 'field field-type-text field-field-event-location'})
                location = location.text.strip() if location is not None else ''
            except:
                location = ''
            date = event_soup.find(
                'span', attrs={'class': 'date-display-single'})
            date = date.text.strip() if date is not None else ''
            try:
                starttime = event_soup.find(
                    'span', attrs={'class': 'date-display-start'}).text.strip()
            except:
                starttime = ''
            try:
                endtime = event_soup.find(
                    'span', attrs={'class': 'date-display-end'}).text.strip()
            except:
                endtime = ''
            description = event_soup.find('div', attrs={
                                          'id': 'content-area'}).find('div', attrs={'class': 'content'}).text.strip()
            events.append({
                'title': title,
                'date': date,
                'location': location,
                'description': description,
                'url': event_url,
                'starttime': starttime,
                'endtime': endtime,
                'owner': 'Department of Linguistics'
            })
    return events


def fetch_events_earth_enviromental_science(base_url='https://www.sas.upenn.edu'):
    """
    Fetch events from the first page from the Earth and Environmental Science department

    Note: We might need to scrape other pages later
    """
    html_page = requests.get(base_url + '/earth/events')
    page_soup = BeautifulSoup(html_page.content, 'html.parser')

    events = []
    all_events = page_soup.find(
        'div', attrs={'class': 'item-list'}).find_all('li')
    for event in all_events:
        event_url = base_url + event.find('a')['href']
        title = event.find('h3').text.strip()
        presenter = event.find('p', attrs={'presenter'}).text.strip(
        ) if event.find('p', attrs={'presenter'}) is not None else ''
        # event_type = event.find('h4').text if event.find('h4') is not None else ''
        location = event.find('div', attrs={'class': 'location'}).text.strip(
        ) if event.find('div', attrs={'class': 'location'}) is not None else ''
        description = ''
        event_soup = BeautifulSoup(requests.get(
            event_url).content, 'html.parser')
        date = event_soup.find('span', attrs={'class': 'date-display-single'})
        date = date.text if date is not None else ''
        starttime, endtime = find_startend_time(date)
        events.append({
            'title': title,
            'date': date,
            'location': location,
            'description': description,
            'speaker': presenter,
            'starttime': starttime,
            'endtime': endtime,
            'url': event_url,
            'owner': 'Earth and Environmental Science'
        })
    return events


def fetch_events_art_history(base_url='https://www.sas.upenn.edu'):
    """
    Fetch events from Art History Department
    """
    page = requests.get(base_url + '/arthistory/events')
    page_soup = BeautifulSoup(page.content, 'html.parser')
    range_pages = max([int(n_page.text) for n_page in page_soup.find('div',
                                                                     attrs={'class': 'pagination pagination-centered'}).find_all('li') if n_page.text.isdigit()])
    events = []
    for n_page in range(1, range_pages):
        page = requests.get(
            (base_url + '/arthistory/events?&page={}').format(n_page))
        page_soup = BeautifulSoup(page.content, 'html.parser')
        all_events = page_soup.find(
            'div', attrs={'class': 'item-list'}).find_all('li')
        for event in all_events:
            event_url = base_url + event.find('a')['href']
            title = event.find('h3').text if event.find(
                'h3') is not None else ''
            # event_type = event.find('strong').text if event.find('strong') is not None else ''
            date = event.find('span', attrs={'class': 'date-display-single'})
            if date is not None:
                date, event_time = date.attrs.get('content').split('T')
                if '-' in event_time:
                    starttime, endtime = event_time.split('-')
                    try:
                        starttime, endtime = dateutil.parser.parse(starttime).strftime(
                            "%I:%M %p"), dateutil.parser.parse(endtime).strftime("%I:%M %p")
                    except:
                        pass
                else:
                    starttime, endtime = event_time, ''
            else:
                date, starttime, endtime = '', '', ''
            location = event.find('div', attrs={'class': 'location'})
            location = location.text.strip() if location is not None else ''
            event_soup = BeautifulSoup(requests.get(
                event_url).content, 'html.parser')
            description = event_soup.find('div', attrs={'class': 'field-body'})
            description = description.text.strip() if description is not None else ''
            events.append({
                'title': title,
                'date': date,
                'location': location,
                'description': description,
                'starttime': starttime,
                'endtime': endtime,
                'url': event_url,
                'owner': 'Art History'
            })
    return events


def fetch_events_sociology(base_url='https://sociology.sas.upenn.edu'):
    """
    Fetch events Sociology department at https://sociology.sas.upenn.edu/events?page=0
    """
    events = []
    html_page = requests.get(base_url + '/events')
    page_soup = BeautifulSoup(html_page.content, 'html.parser')

    range_pages = max([int(n_page.text) for n_page in
                       page_soup.find('div', attrs={'class': 'item-list'}).find_all('li') if n_page.text.isdigit()])

    for n_page in range(range_pages):
        all_events_url = base_url + '/events?page={}'.format(n_page)
        all_events_soup = BeautifulSoup(requests.get(
            all_events_url).content, 'html.parser')
        all_events = all_events_soup.find('div', attrs={
                                          'id': 'content-area'}).find('div', attrs={'class': 'view-content'}).find_all('li')
        for event_section in all_events:
            event_url = base_url + \
                event_section.find('a')['href'] if event_section.find(
                    'a') is not None else ''
            title = event_section.find('a')
            title = title.text.strip() if title is not None else ''

            date = event_section.find('p', attrs={'class': 'dateline'})
            date = date.text.strip() if date is not None else ''

            location = event_section.find('p', attrs={'class': 'location'})
            location = location.text.strip() if location is not None else ''

            if len(event_url) != 0:
                event_page = BeautifulSoup(requests.get(
                    event_url).content, 'html.parser')
                try:
                    description = event_page.find('div', attrs={
                                                  'class': 'field field-type-text field-field-event-title'}).text.strip()
                except:
                    description = ''
                try:
                    starttime = event_page.find(
                        'span', attrs={'class': 'date-display-start'}).text.strip()
                except:
                    starttime = ''
                try:
                    endtime = event_page.find(
                        'span', attrs={'class': 'date-display-end'}).text.strip()
                except:
                    endtime = ''
            events.append({
                'title': title,
                'date': date,
                'starttime': starttime,
                'endtime': endtime,
                'location': location,
                'description': description,
                'url': event_url,
                'owner': 'Sociology Department'
            })
    return events


def fetch_events_cceb(base_url='https://www.cceb.med.upenn.edu/events'):
    """
    Scrape events from Center for Clinical Epidemiology and Biostatistics (CCEB)
    """
    events = []
    html_page = requests.get(base_url + '/events')
    page_soup = BeautifulSoup(html_page.content, 'html.parser')
    event_section = page_soup.find(
        'div', attrs={'class': 'region-inner region-content-inner'})

    all_events = event_section.find_all('div', attrs={'class': 'views-row'})
    for event in all_events:
        event_url = event.find('a')['href']
        title = event.find('a').text.strip()
        event_id = event_url.split('/')[-1]

        # skip conferences by filtering event_id
        # seminars' event_id contain only number
        if not re.match(r'^\d{1,9}$', event_id):
            continue

        text = """https://events.med.upenn.edu/live/calendar/view/event/event_id/{}?user_tz=IT&synta
        x=%3Cwidget%20type%3D%22events_calendar%22%3E%3Carg%20id%3D%22mini_cal_heat_map%22%3Etrue%3C%2Fa
        rg%3E%3Carg%20id%3D%22thumb_width%22%3E200%3C%2Farg%3E%3Carg%20id%3D%22thumb_height%22%3E200%3C%
        2Farg%3E%3Carg%20id%3D%22hide_repeats%22%3Efalse%3C%2Farg%3E%3Carg%20id%3D%22show_groups%22%3Efa
        lse%3C%2Farg%3E%3Carg%20id%3D%22show_tags%22%3Etrue%3C%2Farg%3E%3Carg%20id%3D%22default_view%22%
        3Eday%3C%2Farg%3E%3Carg%20id%3D%22group%22%3ECenter%20for%20Clinical%20Epidemiology%20and%20Bios
        tatistics%20%28CCEB%29%3C%2Farg%3E%3C%21--start%20excluded%20groups--%3E%3C%21--%20if%20you%20ar
        e%20changing%20the%20excluded%20groups%2C%20they%20should%20also%20be%20changed%20in%20this%20fi
        le%3A%0A%09%2Fpublic_html%2Fpsom-excluded-groups.php--%3E%3Carg%20id%3D%22exclude_group%22%3EAdm
        in%3C%2Farg%3E%3Carg%20id%3D%22exclude_group%22%3ETest%20Import%3C%2Farg%3E%3Carg%20id%3D%22excl
        ude_group%22%3ELiveWhale%3C%2Farg%3E%3Carg%20id%3D%22exclude_group%22%3ETest%20Department%3C%2Fa
        rg%3E%3C%21--end%20excluded%20groups--%3E%3Carg%20id%3D%22webcal_feed_links%22%3Etrue%3C%2Farg%3
        E%3C%2Fwidget%3E""".format(event_id).replace('\n', '').replace(' ', '')
        event_json = requests.get(text).json()
        if len(event_json) != 0:
            date = BeautifulSoup(
                event_json['event']['date'], 'html.parser').text
            date = re.sub(r'((1[0-2]|0?[1-9]):([0-5][0-9])([AaPp][Mm]))',
                          '', date).replace('-', '').replace('EST', '').strip()
            starttime, endtime = BeautifulSoup(
                event_json['event']['date_time'], 'html.parser').text.split('-')
            title = event_json['event']['title']
            location = event_json['event']['location']
            description = BeautifulSoup(
                event_json['event']['description'] or '', 'html.parser').text.strip()
            events.append({
                'title': title,
                'date': date,
                'starttime': starttime,
                'endtime': endtime,
                'location': location,
                'description': description,
                'url': event_url,
                'owner': 'Clinical Epidemiology and Biostatistics (CCEB)'
            })
    return events


def fetch_events_cis(base_url="http://www.cis.upenn.edu/about-cis/events/index.php"):
    """
    Fetch events from CIS department. Scrape this site is a little tricky
    """
    events = []
    page_soup = BeautifulSoup(requests.get(base_url).content, 'html.parser')
    title, date, description, speaker = '', '', '', ''
    for tr in page_soup.find_all('tr'):
        if tr.find('img') is not None:
            events.append({
                'date': date,
                'title': title,
                'description': description,
                'speaker': speaker,
                'url': base_url,
                'owner': 'CIS',
                'starttime': '3:00 PM',
                'endtime': '4:00 PM'
            })
            title, date, description = '', '', ''
        else:
            if tr.find('div', attrs={'class': 'CollapsiblePanelContent'}) is not None:
                description = tr.find(
                    'div', attrs={'class': 'CollapsiblePanelContent'}).text.strip()
            if tr.find('div', attrs={'class': 'CollapsiblePanelContent'}) is None:
                event_header = tr.find('td')
                if event_header is not None:
                    date = tr.find('strong').text.strip() if tr.find(
                        'strong') is not None else ''
                    title = ' '.join(tr.text.replace(date, '').strip().split())
    return events


def fetch_events_dsl(base_url='http://dsl.cis.upenn.edu/seminar/'):
    """
    Scrape events from DSL seminar.
    The DSL Seminar is a weekly gathering of the research students and professors in the Distributed Systems Laboratory
    """
    page_soup = BeautifulSoup(requests.get(base_url).content, 'html.parser')
    events_list = page_soup.find('table').find_all('tr')
    events = []
    for event in events_list[1::]:
        date = event.find('td', attrs={'class': 'ms-grid5-left'}).text
        speaker = event.find('td', attrs={'class': 'ms-grid5-even'}).text
        description = event.find_all(
            'td', attrs={'class': 'ms-grid5-even'})[-1].text.strip()
        if 'Abstract' in description:
            title = description.split('Abstract')[0].strip()
            description = ' '.join(description.split('Abstract')[1::]).strip()
            description = ' '.join(description.split())
        else:
            title = description
            description = description
        events.append({
            'title': title,
            'description': description,
            'date': date,
            'url': base_url,
            'speaker': speaker,
            'owner': 'DSL',
            'location': 'DSL Conference Room',
            'starttime': '12 PM',
            'endtime': '1 PM'
        })
    return events


def fetch_events_CURF(base_url='https://www.curf.upenn.edu'):
    """
    Center for Undergrad Research and Fellowship
    """
    page_soup = BeautifulSoup(requests.get(
        base_url + '/curf-events').content, 'html.parser')

    events = []
    event_table = page_soup.find(
        'table', attrs={'class': 'views-table cols-3'})
    all_events = event_table.find_all('tr')
    for event in all_events[1::]:
        title = event.find('div').text
        event_url = base_url + event.find('a')['href']
        date = event.find('span', attrs={'class': 'date-display-single'})
        date = date.text.strip() if date is not None else ''
        description = event.find(
            'td', attrs={'class': 'eventbody'}).text.strip()

        # scrape description directly from ``event_url``
        event_soup = BeautifulSoup(requests.get(
            event_url).content, 'html.parser')
        location = event_soup.find(
            'div', attrs={'class': 'eventlocation'})
        location = location.text.strip() if location is not None else ''
        starttime = find_startend_time(date)[0]
        endtime = event_soup.find('span', attrs={'class': 'date-display-end'})
        endtime = endtime.text.strip() if endtime is not None else ''
        event_details = event_soup.find('div', attrs={'class': 'eventdetails'})
        if event_details is not None:
            event_description = event_details.find(
                'div', attrs={'class': 'eventdescription'})
            if event_description is not None:
                description = event_description.text.replace(
                    'Description:', '').strip()

        events.append({
            'title': title,
            'description': description,
            'url': event_url,
            'date': date,
            'location': location,
            'starttime': starttime,
            'endtime': endtime,
            'owner': 'Center for Undergrad Research and Fellowship (CURF)',
        })
    return events


def fetch_events_upibi(base_url='http://upibi.org/events/list/?tribe_paged=1&tribe_event_display=past'):
    """
    Fetch events from Institute for Biomedical Informatics, http://upibi.org/events/

    TO DO: scrape event's description from URL, fix try and except
    """
    events = []
    page_soup = BeautifulSoup(requests.get(base_url).content, 'html.parser')
    all_events = page_soup.find_all('div',
                                    attrs={'class': 'type-tribe_events'})
    events = []
    for event in all_events:
        try:
            title = event.find('h3').text.strip()
            date = event.find(
                'div', attrs={'class': 'tribe-event-schedule-details'}).text.strip()
            starttime, endtime = find_startend_time(date)
            location = event.find('div', attrs={
                                  'class': 'tribe-events-venue-details'}).text.replace('+ Google Map', '').strip()
            description = event.find('div', attrs={
                                     'class': 'tribe-events-list-event-description tribe-events-content description entry-summary'}).text.strip()
            event_url = event.find('a')['href']
            events.append({
                'title': title,
                'description': description,
                'url': event_url,
                'date': date,
                'location': location,
                'starttime': starttime,
                'endtime': endtime,
                'owner': 'Institute for Biomedical Informatics (UPIBI)'
            })
        except:
            pass
    return events


def fetch_events_ldi(base_url='https://ldi.upenn.edu'):
    """
    Fetch events from Leonard & Davis Institute, https://ldi.upenn.edu
    """
    events = []
    page_soup = BeautifulSoup(requests.get(
        base_url + '/events').content, 'html.parser')

    try:
        pages = page_soup.find('ul', attrs={'class': 'pager'}).find_all('li')
        n_pages = max([int(p.text) for p in pages if p.text.isdigit()])
    except:
        n_pages = 1

    for n_page in range(n_pages):
        event_page_url = base_url + '/events?page={}'.format(n_page)
        page_soup = BeautifulSoup(requests.get(
            event_page_url).content, 'html.parser')
        all_events = page_soup.find_all('div', attrs={'class': 'views-row'})
        for event in all_events:
            if event.find('span', attrs={'class': 'date-display-single'}) is not None:
                date = event.find(
                    'span', attrs={'class': 'date-display-single'}).text.strip()
            elif event.find('span', attrs={'class': 'date-display-start'}) is not None:
                date = event.find(
                    'span', attrs={'class': 'date-display-start'}).text.strip()
            location = event.find(
                'div', attrs={'class': 'field-name-field-location'})
            location = location.text.strip() if location is not None else ''
            title = event.find('h2').text.strip() if event.find(
                'h2') is not None else ''
            subtitle = event.find(
                'div', attrs={'class': 'field-name-field-subhead'})
            title = title + ' ({})'.format(subtitle.text.strip()
                                           ) if subtitle is not None else title
            starttime = page_soup.find(
                'span', attrs={'class': 'date-display-start'}).text.strip()
            endtime = page_soup.find(
                'span', attrs={'class': 'date-display-end'}).text.strip()
            try:
                event_url = event.find('h2').find('a')['href']
                event_url = base_url + event_url
                event_soup = BeautifulSoup(requests.get(
                    event_url).content, 'html.parser')
                description = event_soup.find(
                    'div', attrs={'class': 'event-body'}).text.strip()

                speaker = event_soup.find(
                    'div', attrs={'class': 'field-name-field-persons-name'})
                speaker = speaker.text.strip() if speaker is not None else ''
                speaker_affil = event_soup.find(
                    'div', attrs={'class': 'field-name-field-title'})
                speaker_affil = speaker_affil.text.strip() if speaker_affil is not None else ''
                speaker = (speaker + ' ' + speaker_affil).strip()
            except:
                description = ''
                speaker = ''

            if title != '' and description != '':
                events.append({
                    'title': title,
                    'description': description,
                    'date': date,
                    'location': location,
                    'speaker': speaker,
                    'url': event_url,
                    'owner': 'Leonard & Davis Institute (LDI)',
                    'starttime': starttime,
                    'endtime': endtime
                })
    return events


def fetch_events_korean_studies(base_url='https://www.sas.upenn.edu'):
    """
    Fetch events from Korean Studies
    """
    events = []
    page_soup = BeautifulSoup(requests.get(
        base_url + '/koreanstudies/events').content, 'html.parser')

    events = []
    event_table = page_soup.find('ul', attrs={'class': 'unstyled'})
    all_events = event_table.find_all('li', attrs={'class': 'row-fluid'})
    for event in all_events:
        event_url = base_url + event.find('a')['href']
        event_soup = BeautifulSoup(requests.get(
            event_url).content, 'html.parser')
        title = event_soup.find('h1', attrs={'class': 'page-header'})
        title = title.text.strip() if title is not None else ''
        date = event_soup.find('div', attrs={'class': 'field-date'})
        date = date.text.strip() if date is not None else ''
        starttime, endtime = find_startend_time(date)
        description = event_soup.find('div', attrs={'class': 'field-body'})
        description = description.text.strip() if description is not None else ''
        event_speaker = event_soup.find(
            'div', attrs={'class': 'fieldset-wrapper'})
        event_speaker = event_speaker.text.strip() if event_speaker is not None else ''
        events.append({
            'title': title,
            'description': description,
            'url': event_url,
            'date': date,
            'starttime': starttime,
            'endtime': endtime,
            'speaker': event_speaker,
            'owner': 'Korean Studies'
        })
    return events


def fetch_events_cscc(base_url='https://cscc.sas.upenn.edu/'):
    """
    Fetch events from Penn Arts & Sciences, Center for the Study of Contemporary China

    TO DO: Fix try, except in for this function
    """
    events = []
    page_soup = BeautifulSoup(requests.get(base_url).content, 'html.parser')
    all_events = page_soup.find_all('div', attrs={'class': 'events-listing'})

    for div in all_events:
        try:
            title = div.find(
                'h3', attrs={'class': 'events-title'}).text.strip()
            location = div.find('span', attrs={'class': 'news-date'})
            if location is not None and location.find('span') is not None:
                location = location.find('span').text.strip()
            else:
                location = ''
            event_time = div.find('span', attrs={
                                  'class': 'news-date'}).text.replace('\n', ' ').replace(location, '').strip()
            event_date = div.find('div', attrs={'class': 'event-date'})
            event_date = ' '.join(
                [t.text for t in event_date.find_all('time')])
            starttime, endtime = find_startend_time(event_time)
            speaker = div.find_all('h5')[-1].text
            event_url = base_url + div.find('a')['href']
            event_soup = BeautifulSoup(requests.get(
                event_url).content, 'html.parser')
            description = event_soup.find(
                'div', attrs={'class': 'events-page'}).find('div', attrs={'class': 'body'})
            description = description.text.strip() if description is not None else ''
            events.append({
                'title': title,
                'location': location,
                'date': event_date,
                'starttime': starttime,
                'endtime': endtime,
                'speaker': speaker,
                'url': event_url,
                'description': description,
                'owner': 'Center for the Study of Contemporary China'
            })
        except:
            pass
    return events


def fetch_events_fels(base_url='https://www.fels.upenn.edu'):
    """
    Fetch events from Fels institute of Government at University of Pennsylvania
    """
    events = []
    page_soup = BeautifulSoup(requests.get(
        base_url + '/events').content, 'html.parser')
    all_events = page_soup.find('div', attrs={'class': 'view-content'})
    event_urls = [base_url + a['href']
                  for a in all_events.find_all('a') if a is not None]

    for event_url in event_urls:
        event_soup = BeautifulSoup(requests.get(
            event_url).content, 'html.parser')
        title = event_soup.find('h1', attrs={'id': 'page-title'}).text.strip()
        description = event_soup.find(
            'div', attrs={'class': 'field-name-body'}).text.strip()
        location = event_soup.find(
            'div', attrs={'class': 'field-name-field-event-location'})
        location = location.text.replace(
            "Location Address:", '').strip() if location is not None else ''
        room = event_soup.find(
            'div', attrs={'class': 'field-name-field-event-location-name'})
        room = room.text.replace(
            'Location Name:', '').strip() if room is not None else ''
        date = event_soup.find(
            'span', attrs={'class': 'date-display-single'}).text.strip()
        starttime, endtime = find_startend_time(date)
        location = (location + ' ' + room).strip()
        speaker = event_soup.find('div', attrs={'class': 'breadcrumb-top'})
        speaker = speaker.text.replace(
            'Home\xa0 // \xa0', '').strip() if speaker is not None else ''
        events.append({
            'title': title,
            'location': location,
            'date': date,
            'starttime': starttime,
            'endtime': endtime,
            'description': description,
            'speaker': speaker,
            'url': event_url,
            'owner': 'Fels institute'
        })
    return events


def fetch_events_sciencehistory(base_url='https://www.sciencehistory.org'):
    """
    Fetch events from Science History Institute, https://www.sciencehistory.org/events
    """
    events = []
    page_soup = BeautifulSoup(requests.get(
        base_url + '/events').content, 'html.parser')

    all_events = page_soup.find('div', attrs={'class': 'eventpageleft'})
    all_events = all_events.find_all('div', attrs={'class': 'views-row'})

    for event in all_events:
        title = event.find('div', attrs={'class': 'eventtitle'}).text.strip()
        date = event.find('div', attrs={'class': 'eventdate'}).text.strip()
        event_url = base_url + \
            event.find('div', attrs={'class': 'eventtitle'}).find('a')['href']
        event_soup = BeautifulSoup(requests.get(
            event_url).content, 'html.parser')
        location = event_soup.find('div', attrs={'class': 'event-location'})
        location = ', '.join(
            [div.text.strip() for div in location.find_all('div') if div is not None])
        event_time = event_soup.find('div', attrs={'class': 'event-time'})
        event_time = event_time.text.strip() if event_time is not None else ''
        starttime, endtime = find_startend_time(event_time)

        descriptions = event_soup.find_all('p')
        if len(descriptions) >= 5:
            descriptions = ' '.join([p.text.strip()
                                     for p in descriptions[0:5]])
        else:
            descriptions = ' '.join([p.text.strip() for p in descriptions])

        events.append({
            'title': title,
            'description': descriptions,
            'date': date,
            'starttime': starttime,
            'endtime': endtime,
            'location': location,
            'url': event_url,
            'owner': 'Science History Institute'
        })
    return events


def fetch_events_HIP(base_url='https://www.impact.upenn.edu/'):
    """
    Penn Events for Center for High Impact Philanthropy
    """
    page_soup = BeautifulSoup(requests.get(
        base_url + 'events/').content, 'html.parser')

    events = []
    event_table = page_soup.find('div', attrs={'class': 'entry-content'})
    all_events = event_table.find_all('article')
    for event in all_events:
        event_url = event.find(
            'h2', attrs={'class': 'entry-title'}).find('a')['href']
        date = [p.text for p in event.find_all('p') if '| Event' in p.text][0]
        date = date.replace('| Event', '')

        event_soup = BeautifulSoup(requests.get(
            event_url).content, 'html.parser')
        title = event_soup.find('h1', attrs={'class': 'entry-title'})
        title = title.text.strip() if title is not None else ''

        description = event_soup.find(
            'div', attrs={'class': 'entry-content clearfix'})
        starttime = str(description.find('p')).split(
            '<br/>')[-1].replace('</p>', '') if description is not None else ''

        if description is not None:
            description = ' '.join([i.text.strip() for i in description.find(
                'h3').next_siblings if not isinstance(i, NavigableString)])
        else:
            description = ''

        events.append({
            'title': title,
            'description': description,
            'url': event_url,
            'date': date,
            'starttime': starttime,
            'owner': "Center for High Impact Philanthropy"
        })
    return events


def fetch_events_italian_studies(base_url='https://www.sas.upenn.edu'):
    """
    Penn Events for Italian Studies
    """
    page_soup = BeautifulSoup(requests.get(
        base_url + '/italians/center/events').content, 'html.parser')

    events = []
    event_table = page_soup.find('div', attrs={'class': 'view-content'})
    all_events = event_table.find_all('div', attrs={'class': 'field-content'})
    for event in all_events:
        event_url = base_url + event.find('a')['href']
        event_soup = BeautifulSoup(requests.get(
            event_url).content, 'html.parser')
        title = event_soup.find('h1', attrs={'class': 'title'})
        title = title.text.strip() if title is not None else ''
        date = event_soup.find(
            'span', attrs={'class': 'date-display-single'}).text.strip()

        starttime = event_soup.find(
            'div', attrs={'class': 'field field-type-datetime field-field-event-time'})
        starttime = starttime.text.replace(
            'Time:', '').strip() if starttime is not None else ''
        if starttime is '':
            starttime = event_soup.find(
                'span', attrs={'class': 'date-display-start'}).text.strip()
            endtime = event_soup.find(
                'span', attrs={'class': 'date-display-end'})
            endtime = endtime.text.strip() if endtime is not None else ''
        else:
            starttime, endtime = find_startend_time(starttime)

        page_details = [t.text.strip() for t in event_soup.find_all(
            'div', attrs={'class': 'field-items'})]
        location, speaker = '', ''
        for detail in page_details:
            if 'Speaker' in detail:
                speaker = detail.replace('Speaker:', '').strip()
            if 'Location' in detail:
                location = detail.replace('Location:', '').strip()

        description = event_soup.find(
            'div', attrs={'id': 'content-area'}).find('div', attrs={'class': 'content'})
        description = '\n'.join([t.text for t in description.find_all(
            'p')]) if description is not None else ''
        events.append({
            'title': title,
            'url': event_url,
            'date': date,
            'starttime': starttime,
            'endtime': endtime,
            'location': location,
            'description': description,
            'speaker': speaker,
            'owner': 'Italian Studies'
        })
    return events


def fetch_events_CEMB(base_url='https://cemb.upenn.edu'):
    """
    Penn Events for Center for Engineering MechanoBiology
    """
    page_soup = BeautifulSoup(requests.get(
        base_url + '/items/calendar/').content, 'html.parser')

    events = []
    event_table = page_soup.find(
        'div', attrs={'class': 'gumm-layout-element event-layout-element span5'})
    all_events = event_table.find_all('div', attrs={'class': 'event-details'})
    for event in all_events:
        event_url = event.find('a')['href']
        date = event.find('li', attrs={'class': 'event-meta-date'})
        date = date.text.strip() if date is not None else ''
        location = event.find('li', attrs={'class': 'event-meta-location'})
        location = location.text.strip() if location is not None else ''

        event_soup = BeautifulSoup(requests.get(
            event_url).content, 'html.parser')
        title = event_soup.find('h1')
        title = title.text.strip() if title is not None else ''
        details = event_soup.find('div', attrs={'class': 'event-details'})
        details = details.text.strip() if details is not None else ''

        starttime, endtime = '', ''
        try:
            ts = date.split('•')[-1].strip()
            ts = ts.split('–')
            if len(ts) == 1:
                starttime, endtime = ts[0], ''
            elif len(ts) == 2:
                starttime, endtime = ts[0], ts[1]
            else:
                starttime, endtime = '', ''
        except:
            pass
        starttime, endtime = starttime.strip(), endtime.strip()

        events.append({
            'title': title,
            'date': date,
            'starttime': starttime,
            'endtime': endtime,
            'location': location,
            'url': event_url,
            'description': details,
            'owner': 'Center for Engineering MechanoBiology'
        })
    return events


def fetch_events_CEAS(base_url='https://ceas.sas.upenn.edu'):
    """
    Penn Events for Center for East Asian Studies
    """
    page_soup = BeautifulSoup(requests.get(
        base_url + '/events').content, 'html.parser')

    events = []
    all_events = page_soup.find_all('li', attrs={'class': 'views-row'})
    for event in all_events:
        event_url = base_url + event.find('a')['href']
        event_soup = BeautifulSoup(requests.get(
            event_url).content, 'html.parser')
        title = event_soup.find('h1', attrs={'class': 'page-header'})
        title = title.text.strip() if title is not None else ''
        date = event_soup.find(
            'span', attrs={'class': 'date-display-single'})
        date = date.text.strip() if date is not None else ''
        starttime, endtime = find_startend_time(date)
        details = event_soup.find('div', attrs={
                                  'class': 'field field-name-body field-type-text-with-summary field-label-hidden'})
        details = details.text if details is not None else ''
        events.append({
            'title': title,
            'date': date,
            'starttime': starttime,
            'endtime': endtime,
            'url': event_url,
            'description': details,
            'owner': 'Center for East Asian Studies'
        })
    return events


def fetch_events_CASI(base_url='https://casi.ssc.upenn.edu'):
    """
    Penn Events for Center for the Advanced Study of India
    """
    page_soup = BeautifulSoup(requests.get(
        base_url + '/events').content, 'html.parser')

    events = []
    event_table = page_soup.find(
        'div', attrs={'class': 'main-container container'})
    all_events = event_table.find_all('div', attrs={'class': 'views-row'})
    for event in all_events:
        event_url = base_url + event.find('a')['href']
        event_soup = BeautifulSoup(requests.get(
            event_url).content, 'html.parser')
        title = event_soup.find('h1', attrs={'class': 'page-header'})
        title = title.text.strip() if title is not None else ''
        date = event_soup.find('span', attrs={'class': 'date-display-single'})
        date = date.text.strip() if date is not None else ''
        starttime, endtime = find_startend_time(date)
        details = event_soup.find('div', attrs={
                                  'class': 'field field-name-body field-type-text-with-summary field-label-hidden'})
        details = details.text.strip() if details is not None else ''
        events.append({
            'title': title,
            'date': date,
            'starttime': starttime,
            'endtime': endtime,
            'description': details,
            'url': event_url,
            'owner': 'Center for the Advanced Study of India'
        })
    return events


def fetch_events_african_studies(base_url='https://africana.sas.upenn.edu'):
    """
    Penn Events for African Studies
    site available at https://africana.sas.upenn.edu/center/events
    """
    page_soup = BeautifulSoup(requests.get(
        base_url + '/center/events').content, 'html.parser')

    events = []
    event_table = page_soup.find('div', attrs={'class': 'body-content'})
    all_events = event_table.find_all('div', attrs={'class': 'views-row'})
    for event in all_events:
        event_url = base_url + event.find('a')['href']
        event_soup = BeautifulSoup(requests.get(
            event_url).content, 'html.parser')
        title = event_soup.find('h1', attrs={'class': 'page-header'})
        title = title.text.strip() if title is not None else ''
        speaker = event_soup.find('div', attrs={'class': 'field-speaker'})
        speaker = speaker.text.strip() if speaker is not None else ''
        date = event_soup.find(
            'div', attrs={'class': 'container-date-wrapper'})
        date = date.text.strip() if date is not None else ''
        event_time = event_soup.find(
            'span', attrs={'class': 'date-display-single'})
        event_time = event_time.text.strip() if event_time is not None else ''
        starttime, endtime = find_startend_time(event_time)

        details = event_soup.find('div', attrs={'class': 'field-body'})
        details = details.text.strip() if details is not None else ''
        events.append({
            'title': title,
            'speaker': speaker,
            'date': date,
            'starttime': starttime,
            'endtime': endtime,
            'description': details,
            'url': event_url,
            'owner': 'African Studies'
        })
    return events


def fetch_events_business_ethics(base_url='https://zicklincenter.wharton.upenn.edu'):
    """
    Penn Events for Carol and Lawrence Zicklin Center for Business Ethics Research:
    """
    page_soup = BeautifulSoup(requests.get(
        base_url + '/upcoming-events/').content, 'html.parser')

    events = []
    event_table = page_soup.find('div', attrs={'class': 'post-entry'})
    all_events = event_table.find_all(
        'div', attrs={'class': 'eventrocket embedded-event post'})
    for event in all_events:
        event_url = event.find('a')['href']
        event_soup = BeautifulSoup(requests.get(
            event_url).content, 'html.parser')
        title = event_soup.find('h1', attrs={'class': 'beta'})
        title = title.text.strip() if title is not None else ''
        date = event_soup.find('p', attrs={'class': 'gamma mobile-date'})
        date = date.text.strip() if date is not None else ''
        event_time = event_soup.find(
            'h3').text if event_soup.find('h3') is not None else ''
        starttime, endtime = find_startend_time(event_time)

        details = event_soup.find(
            'div', attrs={'class': 'tribe-events-content-wrapper'})
        details = details.text.strip() if details is not None else ''
        events.append({
            'title': title,
            'date': date,
            'starttime': starttime,
            'endtime': endtime,
            'description': details,
            'url': event_url,
            'owner': 'Zicklincenter Center for Business Ethics'
        })
    return events


def fetch_events_law(base_url='https://www.law.upenn.edu/institutes/legalhistory/workshops-lectures.php'):
    """
    Fetch event from Penn Law School
    """
    events = []
    page_soup = BeautifulSoup(requests.get(base_url).content, 'html.parser')
    all_events = page_soup.find_all('div', attrs={'class': 'lw_events_day'})
    for event in all_events:
        event_id = ''.join([c for c in event.find('a')['href'] if c.isdigit()])
        event_url = '''
        https://www.law.upenn.edu/live/calendar/view/event/event_id/{}?user_tz=IT&syntax=%3Cwidget%20type%3D%22events_calendar%22%20priority%3D%22high%22%3E%3Carg%20id%3D%22mini_cal_heat_map%22%3Etrue%3C%2Farg%3E%3Carg%20id%3D%22exclude_tag%22%3ELibrary%20Hours%3C%2Farg%3E%3Carg%20id%3D%22exclude_tag%22%3ELibrary%20Event%20Private%3C%2Farg%3E%3Carg%20id%3D%22exclude_tag%22%3ECareers%20Calendar%20ONLY%3C%2Farg%3E%3Carg%20id%3D%22exclude_tag%22%3EDocs%20Only%20Event%3C%2Farg%3E%3Carg%20id%3D%22exclude_tag%22%3EPending%20Event%3C%2Farg%3E%3Carg%20id%3D%22exclude_tag%22%3EPrivate%20Event%3C%2Farg%3E%3Carg%20id%3D%22exclude_tag%22%3EOffcampus%3C%2Farg%3E%3Carg%20id%3D%22exclude_group%22%3ERegistrar%3C%2Farg%3E%3Carg%20id%3D%22exclude_group%22%3EAdmitted%20JD%3C%2Farg%3E%3Carg%20id%3D%22placeholder%22%3ESearch%20Calendar%3C%2Farg%3E%3Carg%20id%3D%22disable_timezone%22%3Etrue%3C%2Farg%3E%3Carg%20id%3D%22thumb_width%22%3E144%3C%2Farg%3E%3Carg%20id%3D%22thumb_height%22%3E144%3C%2Farg%3E%3Carg%20id%3D%22modular%22%3Etrue%3C%2Farg%3E%3Carg%20id%3D%22default_view%22%3Eweek%3C%2Farg%3E%3C%2Fwidget%3E
        '''.strip().format(event_id)
        event_detail = requests.get(url=event_url).json()
        event_time = BeautifulSoup(
            event_detail['event']['date_time'], 'html.parser').text
        starttime, endtime = find_startend_time(event_time)
        events.append({
            'date': event_detail['title'],
            'title': event_detail['event']['title'],
            'starttime': starttime,
            'endtime': endtime,
            'event_id': event_id,
            'summary': BeautifulSoup(event_detail['event'].get('summary', ''), 'html.parser').text.strip(),
            'location': event_detail['event']['location'],
            'description': BeautifulSoup(event_detail['event'].get('description', ''), 'html.parser').text.strip(),
            'url': 'https://www.law.upenn.edu/newsevents/calendar.php#event_id/{}/view/event'.format(event_id),
            'owner': 'Penn Law School'
        })
    return events


def fetch_events_penn_SAS(base_url='https://www.sas.upenn.edu'):
    """
    Penn Events for Penn SAS
    """
    page_soup = BeautifulSoup(requests.get(
        base_url + '/events/upcoming-events').content, 'html.parser')

    events = []
    event_table = page_soup.find(
        'div', attrs={'class': 'field-basic-page-content'})
    all_events = event_table.find_all(
        'div', attrs={'class': 'flex-event-desc'})
    for event in all_events:
        event_url = base_url + event.find('a')['href']
        event_soup = BeautifulSoup(requests.get(
            event_url).content, 'html.parser')
        title = event_soup.find('h3', attrs={'class': 'event-title'})
        title = title.text.strip() if title is not None else ''
        date = event_soup.find(
            'div', attrs={'class': 'field-event-start-date'})
        date = date.text.strip() if date is not None else ''
        starttime, endtime = find_startend_time(date)
        location = event_soup.find('div', attrs={'class': 'event-sub-info'})
        location = location.text.strip() if location is not None else ''
        speaker = event_soup.find(
            'div', attrs={'class': 'field-event-speaker'})
        speaker = speaker.text.strip() if speaker is not None else ''
        details = event_soup.find('div', attrs={'class': 'field-event-desc'})
        details = details.text.strip() if details is not None else ''
        events.append({
            'title': title,
            'date': date,
            'starttime': starttime,
            'endtime': endtime,
            'location': location,
            'speaker': speaker,
            'description': details,
            'url': event_url,
            'owner': 'Penn SAS'
        })
    return events


def fetch_events_physics_astronomy(base_url='https://www.physics.upenn.edu'):
    """
    Penn Events Penn Physics and Astronomy Department
    """
    page_soup = BeautifulSoup(requests.get(
        base_url + '/events/').content, 'html.parser')
    try:
        pagination = page_soup.find('ul', attrs={'class': 'pagination'})
        pagination_max = max([a.attrs.get('href')
                              for a in pagination.find_all('a')])
        pagination_max = int(pagination_max[-1])
    except:
        pagination_max = 1

    events = []
    for pagination in range(0, pagination_max):
        page_soup = BeautifulSoup(requests.get(
            base_url + '/events/' + '?page={}'.format(pagination)).content, 'html.parser')
        all_events = page_soup.find_all(
            'div', attrs={'class': 'events-listing'})
        for event in all_events:
            event_url = base_url + event.find('a')['href']
            event_soup = BeautifulSoup(requests.get(
                event_url).content, 'html.parser')
            title = event_soup.find('h3', attrs={'class': 'events-title'})
            title = title.text.strip() if title is not None else ''
            date = event_soup.find('div', attrs={'class': 'event-date'})
            date = ' '.join([d.text.strip() for d in date.find_all('time') if d is not None])
            try:
                event_time = event_soup.find('span', attrs={'class': 'news-date'})
                starttime, endtime = event_time.find_all('time')
                starttime, endtime = starttime.text.strip() or '', endtime.text.strip() or ''
            except:
                starttime, endtime = '', ''
            speaker = ' '.join([h5.text.strip() if h5.text is not None else ''
                                for h5 in event.find_all('h5')]).strip()
            description = event_soup.find('p')
            description = description.text.strip() if description is not None else ''
            events.append({
                'title': title,
                'date': date,
                'starttime': starttime,
                'endtime': endtime,
                'speaker': speaker,
                'description': description,
                'url': event_url,
                'owner': 'Department of Physics and Astronomy'
            })
    return events


def fetch_events_wolf_humanities(base_url='http://wolfhumanities.upenn.edu'):
    """
    Wolf Humanities Center Events, http://wolfhumanities.upenn.edu/events/color
    """
    page_soup = BeautifulSoup(requests.get(
        base_url + '/events/color').content, 'html.parser')

    events = []
    event_table = page_soup.find('div', attrs={'class': 'event-list'})
    all_events = event_table.find_all('li', attrs={'class': 'clearfix'})
    for event in all_events:
        event_url = base_url + event.find('a')['href']
        event_soup = BeautifulSoup(requests.get(
            event_url).content, 'html.parser')
        title = event_soup.find('h1')
        title = title.text.strip() if title is not None else ''
        date = event_soup.find('p', attrs={'class': 'field-date'})
        date = date.text.strip() if date is not None else ''
        starttime, endtime = find_startend_time(date)
        location = event_soup.find('div', attrs={'class': 'field-location'})
        location = location.text.strip() if location is not None else ''
        details = event_soup.find('div', attrs={'class': 'field-body'})
        details = details.text.strip() if details is not None else ''
        events.append({
            'title': title,
            'date': date,
            'starttime': starttime,
            'endtime': endtime,
            'location': location,
            'description': details,
            'url': event_url,
            'owner': 'Wolf Humanities Center Events'
        })
    return events


def fetch_events_music_dept(base_url='https://www.sas.upenn.edu'):
    """
    Department of Music... details does not output anything
    """
    page_soup = BeautifulSoup(requests.get(
        base_url + '/music/performance/performance-calendar').content, 'html.parser')

    events = []
    event_table = page_soup.find('div', attrs={'class': 'view-content'})
    all_events = event_table.find_all('li', attrs={'class': 'group'})
    for event in all_events:
        event_url = base_url + event.find('a')['href']
        event_soup = BeautifulSoup(requests.get(
            event_url).content, 'html.parser')
        title = event_soup.find('h1', attrs={'class': 'title'})
        title = title.text.strip() if title is not None else ''
        date = event_soup.find(
            'div', attrs={'class': 'field field-type-date field-field-events-date'})
        date = date.text.strip() if date is not None else ''
        details = event_soup.find('div', attrs={'class': 'content'})
        details = '\n'.join([p.text.strip() for p in details.find_all(
            'p')]) if details is not None else ''
        starttime, endtime = find_startend_time(date)
        events.append({
            'title': title,
            'date': date,
            'starttime': starttime,
            'endtime': endtime,
            'description': details.strip(),
            'url': event_url,
            'owner': 'Department of Music'
        })
    return events


def fetch_events_annenberg(base_url='https://www.asc.upenn.edu'):
    """
    Penn Events for Annenberg School of Communication
    """
    page_soup = BeautifulSoup(requests.get(
        base_url + '/news-events/events').content, 'html.parser')

    events = []
    event_table = page_soup.find('div', attrs={'id': 'content'})
    all_events = event_table.find_all('h3', attrs={'class': 'field-content'})
    for event in all_events:
        try:
            event_url = base_url + event.find('a')['href']
            event_soup = BeautifulSoup(requests.get(
                event_url).content, 'html.parser')
            title = event_soup.find('h1', attrs={'class': 'title'})
            title = title.text.strip() if title is not None else ''
            date = event_soup.find(
                'span', attrs={'class': 'date-display-single'})
            date = date.text.strip() if date is not None else ''
            starttime, endtime = find_startend_time(date)
            location = event_soup.find('div', attrs={
                                       'class': 'field field-name-field-event-location field-type-text field-label-inline clearfix'})
            location = location.text.strip() if location is not None else ''
            details = event_soup.find('div', attrs={
                                      'class': 'field field-name-body field-type-text-with-summary field-label-hidden'})
            details = details.text.strip() if details is not None else ''
            events.append({
                'title': title,
                'date': date,
                'location': location,
                'description': details,
                'url': event_url,
                'speaker': '',
                'starttime': starttime,
                'endtime': endtime,
                'owner': 'Annenberg School of Communication'
            })
        except:
            pass
    return events


def fetch_events_religious_studies(base_url='https://www.sas.upenn.edu'):
    """
    Penn Events for Department of Religious Studies
    """
    page_soup = BeautifulSoup(requests.get(
        base_url + '/religious_studies/news').content, 'html.parser')

    events = []
    event_table = page_soup.find('div', attrs={'id': 'content-area'})
    all_events = event_table.find_all('div', attrs={'class': 'views-row'})
    for event in all_events:
        event_url = base_url + event.find('a')['href']
        event_soup = BeautifulSoup(requests.get(
            event_url).content, 'html.parser')
        title = event_soup.find('h1', attrs={'class': 'title'})
        title = title.text.strip() if title is not None else ''
        date = event_soup.find('span', attrs={'class': 'date-display-single'})
        date = date.text.strip() if date is not None else ''
        starttime, endtime = find_startend_time(date)
        location = event_soup.find(
            'div', attrs={'class': 'field field-type-text field-field-event-location'})
        location = location.text.strip() if location is not None else ''
        details = event_soup.find('div', attrs={'class': 'content'})
        details = '\n'.join([d.text for d in details.find_all(
            'p')]) if details is not None else ''
        events.append({
            'title': title,
            'date': date,
            'location': location,
            'description': details,
            'url': event_url,
            'starttime': starttime,
            'endtime': endtime,
            'owner': 'Department of Religious Studies'
        })
    return events


def fetch_events_AHEAD(base_url='http://www.ahead-penn.org'):
    """
    Penn Events for Penn AHEAD
    """
    page_soup = BeautifulSoup(requests.get(
        base_url + '/events').content, 'html.parser')

    events = []
    event_table = page_soup.find('div', attrs={'id': 'main-content'})
    all_events = event_table.find_all('div', attrs={'class': 'views-row'})
    for event in all_events:
        event_url = base_url + event.find('a')['href']
        event_soup = BeautifulSoup(requests.get(
            event_url).content, 'html.parser')
        title = event_soup.find('h1', attrs={'class': 'title'})
        title = title.text.strip() if title is not None else ''
        date = event_soup.find('span', attrs={'class': 'date-display-single'})
        date = date.text.strip() if date is not None else ''
        starttime, endtime = find_startend_time(date)
        location = event_soup.find('div', attrs={
                                   'class': 'field field-name-field-location field-type-text field-label-hidden'})
        location = location.text.strip() if location is not None else ''
        details = event_soup.find('div', attrs={
                                  'class': 'field field-name-body field-type-text-with-summary field-label-hidden'})
        details = details.text.strip() if details is not None else ''
        events.append({
            'title': title,
            'date': date,
            'location': location,
            'description': details,
            'url': event_url,
            'starttime': starttime,
            'endtime': endtime,
            'owner': 'Penn AHEAD',
        })
    return events


def fetch_events_SPP(base_url='https://www.sp2.upenn.edu'):
    """
    Penn Events for Penn Social Policy & Practice
    """
    page_soup = BeautifulSoup(requests.get(
        base_url + '/sp2-events/list/').content, 'html.parser')

    events = []
    event_table = page_soup.find('div', attrs={'id': 'tribe-events-content'})
    all_events = event_table.find_all(
        'h2', attrs={'class': 'tribe-events-list-event-title entry-title summary'})
    for event in all_events:
        event_url = event.find('a')['href']
        event_soup = BeautifulSoup(requests.get(
            event_url).content, 'html.parser')
        title = event_soup.find('div', attrs={'class': 'events-header'})
        title = title.text.strip() if title is not None else ''
        date = event_soup.find('h3', attrs={'class': 'date-details-top'})
        date = date.text.strip() if date is not None else ''
        time = event_soup.find('p', attrs={'class': 'event-time-detail'})
        time = time.text.strip() if time is not None else ''
        starttime, endtime = find_startend_time(time)

        details = event_soup.find('div', attrs={
                                  'class': 'tribe-events-single-event-description tribe-events-content entry-content description'})
        details = details.text.strip() if details is not None else ''
        events.append({
            'title': title,
            'date': date,
            'starttime': starttime,
            'endtime': endtime,
            'description': details,
            'url': event_url,
            'owner': 'Penn Social Policy & Practice'
        })
    return events


def fetch_events_ortner_center(base_url='http://ortnercenter.org'):
    """
    Penn Events for Ortner Center for Violence and Abuse in Relationships,
    ref: http://ortnercenter.org/updates?tag=events
    """
    page_soup = BeautifulSoup(requests.get(
        base_url + '/updates?tag=events').content, 'html.parser')

    events = []
    event_table = page_soup.find(
        'div', attrs={'class': 'block content columnBlog--left'})
    all_events = event_table.find_all('div', attrs={'class': 'blog-title'})
    for event in all_events:
        event_url = base_url + event.find('a')['href']
        event_soup = BeautifulSoup(requests.get(
            event_url).content, 'html.parser')
        title = event_soup.find('h6')
        title = title.text.strip() if title is not None else ''
        date = event_soup.find('div', attrs={'class': 'blog-date'})
        date = date.text.strip() if date is not None else ''
        details = event_soup.find('div', attrs={'class': 'apos-content'})
        details = details.text.strip() if details is not None else ''
        events.append({
            'title': title,
            'date': date,
            'starttime': '',
            'endtime': '',
            'description': details,
            'url': event_url,
            'owner': 'Ortner Center for Violence and Abuse in Relationships'
        })
    return events


def fetch_events_penn_today(base_url='https://penntoday.upenn.edu'):
    """
    Penn Today Events
    """
    events = requests.get(
        'https://penntoday.upenn.edu/events-feed?_format=json').json()
    events_list = []
    for event in events:
        events_list.append({
            'event_id': event['id'],
            'title': event['title'],
            'description': BeautifulSoup(event['body'], 'html.parser').text.strip(),
            'date': event['start'],
            'starttime': event['starttime'],
            'endtime': event['endtime'],
            'location': event['location'] if event['location'] is not False else '',
            'url': base_url + event['path'],
            'owner': 'Penn Today Events'
        })
    return events_list


def fetch_events_mins(base_url='http://go.activecalendar.com/handlers/query.ashx?tenant=UPennMINS&site=&get=eventlist&page=0&pageSize=-1&total=-1&view=list2.xslt&callback=jQuery19108584306856037709_1568648511516&_=1568648511517'):
    """
    Fetch events from Mahoney Institute for Neuroscience (MINS)
    """
    events = []
    data = requests.get(url=base_url)
    data = json.loads(data.content.decode('ascii').replace(
        'jQuery19108584306856037709_1568648511516(', '')[:-1])
    event_soup = BeautifulSoup(data['html'], 'html.parser')

    dates = []
    event_date_time = [p.text.strip() for p in event_soup.find_all('p')]
    for e in event_date_time:
        date = dateutil.parser.parse(e.split(', ')[0]).strftime('%d-%m-%Y')
        starttime, endtime = e.split(', ')[1].split('-')
        starttime, endtime = ' '.join(
            starttime.split()), ' '.join(endtime.split())
        dates.append([date, starttime, endtime])
    urls = [h4.find('a').attrs['href'] for h4 in event_soup.find_all('h4')]
    titles = [h4.find('a').attrs.get('aria-label', '') if h4.find('a') is not None else ''
              for h4 in event_soup.find_all('h4')]

    events_descriptions, locations = [], []
    for url in urls:
        event_slug = url.strip('/').split('/')[-1]
        event_url = 'http://go.activecalendar.com/handlers/query.ashx?tenant=UPennMINS&site=&get=eventdetails&route={}&view=detail.xslt'.format(
            event_slug)
        event_page = requests.get(url=event_url)
        event_detail_html = json.loads(event_page.content.decode(
            'ascii').strip('(').strip(')'))['html']
        event_soup = BeautifulSoup(event_detail_html, 'html.parser')
        event_description = event_soup.find(
            'div', attrs={'itemprop': 'description'}).text
        location = event_soup.find('span', attrs={'itemprop': 'name'}).get_text() + \
            ', ' + \
            event_soup.find(
                'span', attrs={'itemprop': 'streetAddress'}).get_text()
        events_descriptions.append(event_description)
        locations.append(location)

    for title, date, url, description, location in zip(titles, dates, urls, events_descriptions, locations):
        events.append({
            'title': title,
            'description': description,
            'date': date[0],
            'starttime': date[1],
            'endtime': date[2],
            'location': location,
            'url': url,
            'owner': 'Mahoney Institute for Neuroscience (MINS)'
        })
    return events


def extract_mindcore_event_detail(event):
    """
    Extract specific event for MindCORE
    """
    title = event.find('h2', attrs={'class': 'event-title'})
    title = title.text.strip() if title is not None else ''
    date = event.find('div', attrs={'class': 'event-meta-item'})
    date = date.get_text() if date is not None else ''
    description = event.find('div', attrs={'class': 'row event-inner-content'})
    description = description.text.strip() if description is not None else ''
    event_time = event.find('div', attrs={'class': 'event-meta-item event-time'})
    event_time = event_time.text.strip() if event_time is not None else ''
    if '-' in event_time:
        starttime, endtime = event_time.split('-')
    else:
        starttime, endtime = event_time, ''
    event_url = event.find('a').attrs.get('href', '')
    speaker = title.split(':')[-1].strip() if ':' in title else ''

    return {
        'title': title,
        'date': date,
        'location': '',
        'description': description,
        'starttime': starttime,
        'endtime': endtime,
        'url': event_url,
        'speaker': speaker,
        'owner': 'MindCORE'
    }


def fetch_events_mindcore(base_url='http://mindcore.sas.upenn.edu/event-category/all-events/'):
    """
    Fetch events from MindCORE
    """
    events = []
    event_page = requests.get(base_url)
    event_soup = BeautifulSoup(event_page.content, 'html.parser')
    try:
        pagination = event_soup.find('ul', attrs={'class': 'pagination'})
        pagination_urls = []
        for li in pagination.find_all('li'):
            if li.find('a') is not None:
                pagination_urls.append(li.find('a').attrs.get('href'))
        pagination_max = max([int(p.split('/')[-2]) for p in pagination_urls if p != ''])
    except:
        pagination_max = 1

    if len(event_soup.find_all('article')) != 1:
        all_events = event_soup.find('div', attrs={'class': 'calendarp'})
        all_events = all_events.find_all('article')
        for event in all_events:
            events.append(extract_mindcore_event_detail(event))

    if pagination_max > 1:
        for i in range(2, pagination_max + 1):
            event_url = 'http://mindcore.sas.upenn.edu/event-category/all-events/page/{}/'.format(i)
            event_page = requests.get(event_url)
            event_soup = BeautifulSoup(event_page.content, 'html.parser')
            if len(event_soup.find_all('article')) != 1:
                all_events = event_soup.find('div', attrs={'class': 'calendarp'})
                all_events = all_events.find_all('article')
                for event in all_events:
                    events.append(extract_mindcore_event_detail(event))
    return events


def fetch_events_seas(base_url='https://events.seas.upenn.edu/calendar/list/'):
    """
    Fetch events from School Engineering and Applied Science (SEAS)
    """
    events = []
    for i in range(1, 3):
        try:
            event_url = urljoin(base_url, '?tribe_paged={}&tribe_event_display=list'.format(i))
            event_page = BeautifulSoup(requests.get(event_url).content, 'html.parser')
            all_events = event_page.find('div', attrs={'class': 'tribe-events-loop'})
            year = event_page.find('h2', attrs={'class': 'tribe-events-list-separator-month'})
            year = year.text.strip() if year is not None else ''
            for event in all_events.find_all('div', attrs={'class': 'type-tribe_events'}):
                event_attrs = event.find('a', attrs={'class': 'tribe-event-url'}).attrs
                event_url = event_attrs.get('href', '')
                title = event_attrs.get('title', '')
                date = event.find('span', attrs={'class': 'tribe-event-date-start'})
                date = date.text if date is not None else ''
                starttime = find_startend_time(date)[0]
                date = date.replace(starttime, '').replace(' at ', '')
                endtime = event.find('span', attrs={'class': 'tribe-event-time'})
                endtime = endtime.text.strip() if endtime is not None else ''
                if ' ' in year:
                    date = date + ' ' + year.split(' ')[-1]
                location = event.find('div', attrs={'class': 'tribe-events-venue-details'})
                location = ' '.join(location.text.replace('+ Google Map', '').strip().split('\n')[0:2])
                description = event.find('div', attrs={'class': 'tribe-events-list-event-description'})
                description = description.text.strip() if description is not None else ''

                # get description if available
                try:
                    event_soup = BeautifulSoup(requests.get(event_url).content, 'html.parser')
                    description = event_soup.find('div', attrs={'id': 'z5_events_main_content'})
                    if description is not None:
                        description = description.text.strip()
                        description = '\n'.join([d.strip() for d in description.split('\n') if d.strip() != ''])
                    speaker = event_soup.find('div', attrs={'id': 'z5_events_speaker_info'})
                    if speaker is not None:
                        speaker = speaker.text.strip()
                        speaker = '\n'.join([d.strip() for d in speaker.split('\n') if d.strip() != ''])
                except:
                    speaker = ''
                events.append({
                    'title': title,
                    'date': date,
                    'location': location,
                    'description': description,
                    'starttime': starttime,
                    'endtime': endtime,
                    'url': event_url,
                    'speaker': speaker,
                    'owner': 'School of Engineering and Applied Science (SEAS)'
                })
        except:
            pass
    return events


if __name__ == '__main__':
    events = []
    fetch_fns = [
        fetch_events_cni, fetch_events_english_dept, fetch_events_crim,
        fetch_events_mec, fetch_events_biology, fetch_events_economics,
        fetch_events_philosophy, fetch_events_classical_studies, fetch_events_linguistic,
        fetch_events_earth_enviromental_science, fetch_events_art_history, fetch_events_sociology,
        fetch_events_cceb, fetch_events_cis, fetch_events_CURF,
        fetch_events_upibi, fetch_events_ldi, fetch_events_korean_studies,
        fetch_events_cscc, fetch_events_fels, fetch_events_sciencehistory,
        fetch_events_HIP, fetch_events_italian_studies, fetch_events_CEMB,
        fetch_events_CEAS, fetch_events_CASI, fetch_events_african_studies,
        fetch_events_business_ethics, fetch_events_law, fetch_events_penn_SAS,
        fetch_events_physics_astronomy, fetch_events_wolf_humanities, fetch_events_music_dept,
        fetch_events_annenberg, fetch_events_religious_studies, fetch_events_AHEAD,
        fetch_events_SPP, fetch_events_ortner_center, fetch_events_penn_today,
        fetch_events_mins, fetch_events_mindcore, fetch_events_seas
    ]
    for f in tqdm(fetch_fns):
        try:
            events.extend(f())
        except:
            print(f)
    events_df = pd.DataFrame(events).fillna('')
    events_df['date_dt'] = events_df['date'].map(
        lambda x: clean_date_format(x))
    events_df.loc[:, 'starttime'] = events_df.apply(clean_starttime, axis=1)
    events_df.loc[events_df.endtime == '', 'endtime'] = events_df.loc[events_df.endtime == ''].apply(clean_endtime, axis=1)

    # save data
    if not os.path.exists(PATH_DATA):
        events_df = events_df.drop_duplicates(
            subset=['starttime', 'owner', 'location', 'title', 'description', 'url'], keep='first')
        events_df['event_index'] = np.arange(len(events_df))
        save_json(events_df.to_dict(orient='records'), PATH_DATA)
    else:
        events_former_df = pd.DataFrame(
            json.loads(open(PATH_DATA, 'r').read()))
        events_df = pd.concat(
            (events_former_df, events_df), axis=0, sort=False)
        events_df = events_df.drop_duplicates(
            subset=['starttime', 'owner', 'location', 'title', 'description', 'url'], keep='first')
        event_idx_begin = events_former_df['event_index'].max() + 1
        event_idx_end = event_idx_begin + events_df.event_index.isnull().sum()
        events_df.loc[pd.isnull(events_df.event_index), 'event_index'] = np.arange(
            event_idx_begin, event_idx_end)
        events_df['event_index'] = events_df['event_index'].astype(int)
        save_json(events_df.to_dict(orient='records'), PATH_DATA)

    # produce topic vectors using tf-idf and Laten Semantic Analysis (LSA)
    if PRODUCE_VECTOR:
        events_df = pd.DataFrame(json.loads(open(PATH_DATA, 'r').read()))
        events_text = [' '.join([e[1] for e in r.items()])
                       for _, r in events_df[['title', 'description', 'location', 'starttime']].iterrows()]
        events_preprocessed_text = [preprocess(text) for text in events_text]
        tfidf_model = TfidfVectorizer(min_df=3, max_df=0.85,
                                      lowercase=True, norm='l2',
                                      ngram_range=(1, 2),
                                      use_idf=True, smooth_idf=True, sublinear_tf=True,
                                      stop_words='english')
        X_tfidf = tfidf_model.fit_transform(events_preprocessed_text)
        lsa_model = TruncatedSVD(n_components=30,
                                 n_iter=100,
                                 algorithm='arpack')
        lsa_vectors = lsa_model.fit_transform(X_tfidf)
        events_vector = [list(vector) for vector in lsa_vectors]
        events_df['event_vector'] = events_vector
        save_json(events_df[['event_index', 'event_vector']].to_dict(orient='records'), PATH_VECTOR)
