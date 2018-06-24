import shortid from 'shortid';
import moment from 'moment';

class Key {
  static getShortKey() {
    return shortid.generate();
  }
}

class Events {
  static getText(eventItem) {
    return {
      date: eventItem.date._text,
      starttime: eventItem.starttime._text,
      endtime: eventItem.endtime._text,
      title: eventItem.title._text,
      description: eventItem.description._text,
      location: eventItem.location._text,
      room: eventItem.room._text,
      url: eventItem.url._text,
      student: eventItem.student._text,
      privacy: eventItem.privacy._text,
      category: eventItem.category._text,
      school: eventItem.school._text,
      owner: eventItem.owner._text,
      link: eventItem.link._text,
    };
  }
}

class Datetime {
  static getMonthDay(dtStr) {
    return moment(dtStr).format('MM.DD').toString();
  }

  static getTime(timeStr) {
    // console.log(moment(timeStr, 'HH:mm:ss').format('LT'));
    return moment(timeStr, 'HH:mm:ss').format('HH:MM A');
  }
}

export { Datetime, Events, Key };
