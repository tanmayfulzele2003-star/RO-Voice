--
-- PostgreSQL database dump
--

\restrict FLLsxbOXXQwLijUEP1X9mXYFpM8TU2Unf5E2GdT4CU0zcMe1resf9AaEq6fKIBH

-- Dumped from database version 16.14 (Ubuntu 16.14-0ubuntu0.24.04.1)
-- Dumped by pg_dump version 16.14 (Ubuntu 16.14-0ubuntu0.24.04.1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
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
-- Name: business_profiles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.business_profiles (
    id uuid NOT NULL,
    name text NOT NULL,
    agent_name text NOT NULL,
    industry text,
    description text,
    products text,
    call_objective text NOT NULL,
    greeting text,
    language text,
    fields jsonb NOT NULL,
    is_default boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    transfer_number text
);


--
-- Name: call_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.call_events (
    id uuid NOT NULL,
    call_id uuid NOT NULL,
    event_type text NOT NULL,
    detail text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
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
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    follow_up_notes text,
    call_outcome text
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
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    profile_id uuid,
    channel text DEFAULT 'phone'::text NOT NULL,
    outcome text,
    from_number text,
    to_number text,
    phone_number_id uuid,
    campaign_id uuid,
    transferred_to text
);


--
-- Name: campaign_contacts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.campaign_contacts (
    id uuid NOT NULL,
    campaign_id uuid NOT NULL,
    customer_id uuid NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    attempts integer DEFAULT 0 NOT NULL,
    last_call_id uuid,
    last_outcome text,
    next_attempt_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: campaigns; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.campaigns (
    id uuid NOT NULL,
    name text NOT NULL,
    profile_id uuid,
    status text DEFAULT 'draft'::text NOT NULL,
    max_concurrent integer NOT NULL,
    max_attempts integer NOT NULL,
    retry_delay_minutes integer NOT NULL,
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
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
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    purpose text,
    product text,
    profile_id uuid
);


--
-- Name: phone_numbers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.phone_numbers (
    id uuid NOT NULL,
    number text NOT NULL,
    label text,
    profile_id uuid,
    inbound_enabled boolean DEFAULT true NOT NULL,
    outbound_enabled boolean DEFAULT true NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    last_used_at timestamp with time zone,
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
    additional_requirements text,
    fields jsonb
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
-- Name: business_profiles business_profiles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.business_profiles
    ADD CONSTRAINT business_profiles_pkey PRIMARY KEY (id);


--
-- Name: call_events call_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.call_events
    ADD CONSTRAINT call_events_pkey PRIMARY KEY (id);


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
-- Name: campaign_contacts campaign_contacts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.campaign_contacts
    ADD CONSTRAINT campaign_contacts_pkey PRIMARY KEY (id);


--
-- Name: campaigns campaigns_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.campaigns
    ADD CONSTRAINT campaigns_pkey PRIMARY KEY (id);


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
-- Name: phone_numbers phone_numbers_number_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.phone_numbers
    ADD CONSTRAINT phone_numbers_number_key UNIQUE (number);


--
-- Name: phone_numbers phone_numbers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.phone_numbers
    ADD CONSTRAINT phone_numbers_pkey PRIMARY KEY (id);


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
-- Name: campaign_contacts uq_campaign_contacts_customer; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.campaign_contacts
    ADD CONSTRAINT uq_campaign_contacts_customer UNIQUE (campaign_id, customer_id);


--
-- Name: ix_call_events_call_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_call_events_call_id ON public.call_events USING btree (call_id);


--
-- Name: ix_calls_campaign_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_calls_campaign_id ON public.calls USING btree (campaign_id);


--
-- Name: ix_calls_customer_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_calls_customer_id ON public.calls USING btree (customer_id);


--
-- Name: ix_calls_outcome; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_calls_outcome ON public.calls USING btree (outcome);


--
-- Name: ix_calls_phone_number_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_calls_phone_number_id ON public.calls USING btree (phone_number_id);


--
-- Name: ix_calls_profile_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_calls_profile_id ON public.calls USING btree (profile_id);


--
-- Name: ix_calls_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_calls_status ON public.calls USING btree (status);


--
-- Name: ix_campaign_contacts_campaign_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_campaign_contacts_campaign_status ON public.campaign_contacts USING btree (campaign_id, status);


--
-- Name: ix_campaign_contacts_customer_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_campaign_contacts_customer_id ON public.campaign_contacts USING btree (customer_id);


--
-- Name: ix_campaigns_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_campaigns_status ON public.campaigns USING btree (status);


--
-- Name: ix_conversation_messages_call_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_conversation_messages_call_id ON public.conversation_messages USING btree (call_id);


--
-- Name: ix_customers_profile_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_customers_profile_id ON public.customers USING btree (profile_id);


--
-- Name: ix_phone_numbers_profile_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_phone_numbers_profile_id ON public.phone_numbers USING btree (profile_id);


--
-- Name: uq_business_profiles_one_default; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_business_profiles_one_default ON public.business_profiles USING btree (is_default) WHERE is_default;


--
-- Name: call_events call_events_call_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.call_events
    ADD CONSTRAINT call_events_call_id_fkey FOREIGN KEY (call_id) REFERENCES public.calls(id);


--
-- Name: call_summaries call_summaries_call_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.call_summaries
    ADD CONSTRAINT call_summaries_call_id_fkey FOREIGN KEY (call_id) REFERENCES public.calls(id);


--
-- Name: calls calls_campaign_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.calls
    ADD CONSTRAINT calls_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id) ON DELETE SET NULL;


--
-- Name: calls calls_customer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.calls
    ADD CONSTRAINT calls_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.customers(id);


--
-- Name: calls calls_phone_number_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.calls
    ADD CONSTRAINT calls_phone_number_id_fkey FOREIGN KEY (phone_number_id) REFERENCES public.phone_numbers(id) ON DELETE SET NULL;


--
-- Name: calls calls_profile_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.calls
    ADD CONSTRAINT calls_profile_id_fkey FOREIGN KEY (profile_id) REFERENCES public.business_profiles(id) ON DELETE SET NULL;


--
-- Name: campaign_contacts campaign_contacts_campaign_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.campaign_contacts
    ADD CONSTRAINT campaign_contacts_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id) ON DELETE CASCADE;


--
-- Name: campaign_contacts campaign_contacts_customer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.campaign_contacts
    ADD CONSTRAINT campaign_contacts_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.customers(id) ON DELETE CASCADE;


--
-- Name: campaign_contacts campaign_contacts_last_call_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.campaign_contacts
    ADD CONSTRAINT campaign_contacts_last_call_id_fkey FOREIGN KEY (last_call_id) REFERENCES public.calls(id) ON DELETE SET NULL;


--
-- Name: campaigns campaigns_profile_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.campaigns
    ADD CONSTRAINT campaigns_profile_id_fkey FOREIGN KEY (profile_id) REFERENCES public.business_profiles(id) ON DELETE SET NULL;


--
-- Name: conversation_messages conversation_messages_call_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversation_messages
    ADD CONSTRAINT conversation_messages_call_id_fkey FOREIGN KEY (call_id) REFERENCES public.calls(id);


--
-- Name: customers customers_profile_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customers
    ADD CONSTRAINT customers_profile_id_fkey FOREIGN KEY (profile_id) REFERENCES public.business_profiles(id) ON DELETE SET NULL;


--
-- Name: phone_numbers phone_numbers_profile_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.phone_numbers
    ADD CONSTRAINT phone_numbers_profile_id_fkey FOREIGN KEY (profile_id) REFERENCES public.business_profiles(id) ON DELETE SET NULL;


--
-- Name: requirements requirements_call_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.requirements
    ADD CONSTRAINT requirements_call_id_fkey FOREIGN KEY (call_id) REFERENCES public.calls(id);


--
-- PostgreSQL database dump complete
--

\unrestrict FLLsxbOXXQwLijUEP1X9mXYFpM8TU2Unf5E2GdT4CU0zcMe1resf9AaEq6fKIBH

