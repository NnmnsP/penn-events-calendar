import { FontAwesomeIcon as Fa } from '@fortawesome/react-fontawesome';
import PropTypes from 'prop-types';
import React from 'react';
import renderHTML from 'react-render-html';
import styled from 'styled-components';
import { Category } from '../../Data';
import { Datetime as dtutil, Events as evutil } from '../../Utils';

const StyledListItem = styled.li`
  margin-bottom: 10px;
  padding-bottom: 10px;
  border-bottom: 1px solid #eee;
`;

const StyledContentWrapper = styled.div`
  border-left: 3px solid ${props => props.color};
  display: inline-flex;
  flex-direction: row;
`;

const DatetimeWrapper = styled.div`
  font-size: 2rem;
  align-self: center;
  align-items: center;
  justify-content: center;
  padding: 0 20px;
  display: flex;
  flex-direction: column;
`;

const StyledDate = styled.div`
  font-family: 'Source Code Pro';
  padding: 0 3px;
`;

const StyledTime = styled.div`
  text-align: center;
  font-size: 0.75rem;
  display: inline-flex;
`;

const StyledTimeIcon = styled.div`
  align-self: center;
  padding-right: 7px;
  font-size: 0.95rem;
`;

const StyledTitle = styled.div`
  font-size: 1.3rem;
  font-weight: 600;
`;

const StyledLocation = styled.div`
  font-size: 0.9rem;
  padding-top: 5px;
`;

const CatContainer = styled.div`
  display: inline-block;
`;

const StyledCat = styled.div`
  font-size: 0.9rem;
  margin-top: 10px;
  padding: 5px;
  border: 1px solid ${props => props.color};
  background-color: ${props => `${props.color}1A`};
  border-radius: 5px;
  width: auto;
`;

const EventItem = ({ ev }) => (
  <StyledListItem>
    <StyledContentWrapper color={Category.getColor(evutil.getText(ev).category)}>
      <DatetimeWrapper>
        <StyledDate>
          {dtutil.getMonthDay(evutil.getText(ev).date)}
        </StyledDate>
        <StyledTime>
          <StyledTimeIcon>
            <Fa icon="clock" />
          </StyledTimeIcon>
          {dtutil.getTime(evutil.getText(ev).starttime)}
          <br />
          {dtutil.getTime(evutil.getText(ev).endtime)}
        </StyledTime>
      </DatetimeWrapper>
      <div>
        <StyledTitle>
          {renderHTML(evutil.getText(ev).title)}
        </StyledTitle>
        <StyledLocation>
          <Fa icon="map-marker-alt" /> {evutil.getText(ev).location}
        </StyledLocation>
        <CatContainer>
          <StyledCat color={Category.getColor(evutil.getText(ev).category)}>
            {evutil.getText(ev).category}
          </StyledCat>
        </CatContainer>
      </div>
    </StyledContentWrapper>
  </StyledListItem>
);

EventItem.propTypes = {
  ev: PropTypes.object.isRequired,
};

export default EventItem;
