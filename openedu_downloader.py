import re

import lxml.html as html
import requests

from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from getpass import getpass
from pathlib import Path
from progressbar import progress

CHUNK_SIZE = 1024 * 1024


class OpenEduException(Exception):
    pass


class OpenEduLoginException(OpenEduException):
    pass


def get_valid_filename_str(s):
    """Убирает запрещенные символы из имени файла"""
    s = str(s).strip()
    return re.sub(r'(?u)[^-\w.]', '', s)


def create_folder(path, folder_name):
    """Функция создает директорию по заданному пути"""
    cleared_folder_name = re.sub('[^\w_.)( -]', '', folder_name)
    path = (path / cleared_folder_name)
    path.mkdir(parents=True, exist_ok=True)


def downloader(url, filename, file_type='.mp4'):
    """Функция осуществляет загрузку видео-файла по url, в файл filename"""
    filename = filename.with_suffix(file_type)
    r = requests.get(url, stream=True)
    filename_str = str(filename.resolve())
    if not filename.exists():
        total_length = int(r.headers.get('content-length'))
        dl = 0
        if len(filename_str) > 260:
            print("\n{0}\n{1}\nИмена файлов слишком длинны для перемещения в эту целевую папку. Лекции будет присвоено имя формата 'Лекция №'".format(
                *list(map(list, re.findall(r'.*/(.*)/(.*)', filename_str)))[0]) + "\n")
            filename_str = re.findall(
                r'(.*Лекция \d*)', filename_str)[0] + file_type
            filename = Path(filename_str)
        temp_filename = filename.with_suffix('.download')
        with temp_filename.open('wb') as f:
            for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
                dl += len(chunk)
                if chunk:
                    f.write(chunk)
                progress(dl, total_length)
        temp_filename.rename(filename)

    else:
        print('Файл "{}" уже существует'.format(filename))


def authorizer_and_pagegetter(username, password, URL='https://sso.openedu.ru/login/', next_page='/oauth2/authorize%3Fstate%3DYpbWrm0u6VoE6nOvTi47PQLaC5CB5ZFJ%26redirect_uri%3Dhttps%3A//openedu.ru/complete/npoedsso/%26response_type%3Dcode%26client_id%3D808f52636759e3616f1a%26auth_entry%3Dlogin'):
    """
    Функция авторизуется и загружает страницу курса для парсинга.
    Возвращает страницу курса
     """
    client = requests.session()
    retries = Retry(total=5, backoff_factor=1,
                    status_forcelist=[502, 503, 504])
    client.mount('https://', HTTPAdapter(max_retries=retries))
    csrf = client.get(URL).cookies['csrftoken']
    login_data = dict(username=username, password=password,
                      csrfmiddlewaretoken=csrf, next=next_page)
    r = client.post(URL, data=login_data, headers=dict(
        Referer=URL),  allow_redirects=False)
    if r.status_code != 302:
        # Нет редиректа. Неверный логин или пароль
        raise OpenEduLoginException('Неверный логин или пароль')
    return client


def page_parser(page):
    """
    Функция осуществляет парсинг страниц.
    Возвращает словарь со следующе структурой:
    ключ - название модуля, значение - список из 2-х элементов
    первый - название урока, второй - ссылка на страницу урока
    """
    modules = {}
    html_page = html.fromstring(page)
    for module_element in html_page.find_class('outline-item section'):
        module_name = module_element.find_class('section-title')[0].text
        lessons = []
        for lesson_element in module_element.find_class('vertical outline-item focusable'):
            lesson_name = lesson_element.find_class(
                'vertical-title')[0].text_content().strip()
            lesson_url = lesson_element.find_class(
                'outline-item')[1].attrib['href']
            lessons.append([lesson_name, lesson_url])
        modules[module_name] = lessons
    return modules


def content_finder(page):
    """функция ищет все видео с темы + названия видео, а так же ссылки на конспект лекций"""
    video_url_pattern = r'https://video.*?\.mp4'
    title_pattern = r'data-page-title="(.*?)"'
    summary_pattern = r'href=&#34;(.*)&#34; .*Конспект лекции.*/a'
    if re.findall(video_url_pattern, page) != [] and re.findall(title_pattern, page) != []:
        return list(zip(
            re.findall(video_url_pattern, page)[1::],
            re.findall(title_pattern, page),
            # TODO uncomment
            # re.findall(summary_pattern, page)
        ))
    else:
        return 1


def main():
    username = input('Ваш логин или email: ')
    password = getpass('Ваш пароль: ')
    course_url = input(
        'Ссылка на курс (на вкладку "Курс") в виде URL-а на страницу: ').strip()
    download_path = re.sub(
        r'\\', '/', (input('Ссылка на папку  (по умолчанию, текущая папка): ')))
    if download_path == '':
        download_path = '.'
    download_path = Path(download_path)

    course_domain = re.findall(r'(.*)\.ru/.*', course_url)[0] + '.ru'
    client = authorizer_and_pagegetter(username, password)
    page = client.get(course_url).text

    course_name = re.findall(
        r'<div class="coursename-title(.*)">(.*)</div>', page)[0][1]
    course_download_path = download_path / get_valid_filename_str(course_name)

    table = page_parser(page)
    count = 1
    for module_name in table:
        create_folder(course_download_path, module_name)
        total_paths = len(table)
        print('Page {} out of {}:'.format(count, total_paths))
        for j in table[module_name]:
            content_list = content_finder(client.get(j[1]).text)
            g = 1
            if content_list != 1:
                length = len(content_list)
                for content in content_list:
                    video_url = content[0]
                    video_name = content[1]
                    # TODO uncomment
                    summary_url = course_domain  # + '/' + content[2]
                    chapter_name = re.sub('[^\w_.)( -]', '', module_name)
                    numbered_video_name = re.sub('[^\w_.)( -]', '', video_name)

                    print('[{}/{}] Downloading... {}'.format(g, length, video_url))
                    downloader(video_url, course_download_path / chapter_name /
                               "Лекция {} {}".format(g, numbered_video_name))
                    # TODO uncomment
                    # print('[{}/{}] Downloading... {}'.format(g, length, summary_url))
                    # downloader(summary_url, str(download_path) + "/" + chapter_name + "/" + "Конспект {0} ".format(g) + numbered_video_name, file_type = '.pdf')
                    g += 1
        count += 1

    client.close()
    print("Закачка закончена. Если были какие-то замечания или пожелания - напишите, пожалуйста, авторам скрипта.")


if __name__ == '__main__':
    try:
        main()
    except OpenEduLoginException:
        print('\n', 'Неверный логин или пароль')
    except:
        print('\n', 'Проверьте корректность введенных данных и наличие курса.'
              ' \nТочно ссылка на вкладку "Курс"?'
              ' \nВсе верно? Тогда, пожалуйста, сообщите авторам скрипта.'
              ' Вы поможете сделать скрипт еще лучше.')
        raise
