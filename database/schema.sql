--
-- PostgreSQL database dump
--

\restrict aEUc0kkeAJN2VT8hRh188xn5Kg4RN4u3EwB0J0ARVqbh9c6wznXgsMlMgemResw

-- Dumped from database version 17.7
-- Dumped by pg_dump version 17.7

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: admin_users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.admin_users (
    id uuid NOT NULL,
    username text NOT NULL,
    password_hash text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


--
-- Name: call_summaries; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.call_summaries (
    id uuid NOT NULL,
    call_id uuid NOT NULL,
    summary text,
    customer_intent text,
    key_requirements jsonb,
    important_points jsonb,
    follow_up boolean,
    lead_status text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: calls; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.calls (
    id uuid NOT NULL,
    customer_id uuid NOT NULL,
    twilio_call_sid text,
    direction text,
    status text,
    start_time timestamp with time zone,
    end_time timestamp with time zone,
    duration_seconds integer,
    error_reason text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: conversation_messages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.conversation_messages (
    id uuid NOT NULL,
    call_id uuid NOT NULL,
    speaker text NOT NULL,
    message text NOT NULL,
    "timestamp" timestamp with time zone
);


--
-- Name: customers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.customers (
    id uuid NOT NULL,
    name text NOT NULL,
    phone text NOT NULL,
    company text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: requirements; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.requirements (
    id uuid NOT NULL,
    call_id uuid NOT NULL,
    customer_name text,
    company_name text,
    requirement text,
    ro_capacity text,
    location text,
    budget text,
    timeline text,
    additional_requirements text
);


--
-- Name: admin_users admin_users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.admin_users
    ADD CONSTRAINT admin_users_pkey PRIMARY KEY (id);


--
-- Name: admin_users admin_users_username_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.admin_users
    ADD CONSTRAINT admin_users_username_key UNIQUE (username);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: call_summaries call_summaries_call_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.call_summaries
    ADD CONSTRAINT call_summaries_call_id_key UNIQUE (call_id);


--
-- Name: call_summaries call_summaries_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.call_summaries
    ADD CONSTRAINT call_summaries_pkey PRIMARY KEY (id);


--
-- Name: calls calls_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.calls
    ADD CONSTRAINT calls_pkey PRIMARY KEY (id);


--
-- Name: calls calls_twilio_call_sid_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.calls
    ADD CONSTRAINT calls_twilio_call_sid_key UNIQUE (twilio_call_sid);


--
-- Name: conversation_messages conversation_messages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversation_messages
    ADD CONSTRAINT conversation_messages_pkey PRIMARY KEY (id);


--
-- Name: customers customers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customers
    ADD CONSTRAINT customers_pkey PRIMARY KEY (id);


--
-- Name: requirements requirements_call_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.requirements
    ADD CONSTRAINT requirements_call_id_key UNIQUE (call_id);


--
-- Name: requirements requirements_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.requirements
    ADD CONSTRAINT requirements_pkey PRIMARY KEY (id);


--
-- Name: ix_calls_customer_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_calls_customer_id ON public.calls USING btree (customer_id);


--
-- Name: ix_calls_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_calls_status ON public.calls USING btree (status);


--
-- Name: ix_conversation_messages_call_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_conversation_messages_call_id ON public.conversation_messages USING btree (call_id);


--
-- Name: call_summaries call_summaries_call_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.call_summaries
    ADD CONSTRAINT call_summaries_call_id_fkey FOREIGN KEY (call_id) REFERENCES public.calls(id);


--
-- Name: calls calls_customer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.calls
    ADD CONSTRAINT calls_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.customers(id);


--
-- Name: conversation_messages conversation_messages_call_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversation_messages
    ADD CONSTRAINT conversation_messages_call_id_fkey FOREIGN KEY (call_id) REFERENCES public.calls(id);


--
-- Name: requirements requirements_call_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.requirements
    ADD CONSTRAINT requirements_call_id_fkey FOREIGN KEY (call_id) REFERENCES public.calls(id);


--
-- PostgreSQL database dump complete
--

\unrestrict aEUc0kkeAJN2VT8hRh188xn5Kg4RN4u3EwB0J0ARVqbh9c6wznXgsMlMgemResw

