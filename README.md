# 🗽 NYC 311 Explorer

An interactive web app to explore and visualize NYC 311 call data — built with Streamlit.  

## 🚀 What is this

**NYC 311 Explorer** lets you load, filter, and visualize complaint data from the city’s 311 system, helping you to discover patterns in complaint types, response times, geographic distribution, and seasonal trends.  

You can use it to answer questions like:  
- Which neighborhoods report the most noise complaints?  
- How does response time vary across boroughs or agencies?  
- Are there seasonal patterns in 311 complaint volume?  

This app is particularly useful for data-analysts, urban researchers, community advocates, or anyone curious about NYC’s non-emergency service requests.

## 📊 Demo / Access  

You can try the live app here:  
[https://311calls-in9r8rkywe2rjkpfzt5dvr.streamlit.app/](https://311calls-in9r8rkywe2rjkpfzt5dvr.streamlit.app/)  

> ⚠️ This link points to the deployed Streamlit application.  

## 🧰 Features  

- Upload or load historical 311 complaint data  
- Filter by **date range**, **borough**, **complaint type**, **agency**, etc.  
- Visualize: bar charts, line charts, heatmaps, geographic maps (if geo-data is present)  
- Compare complaint volume, response times, and other metrics over time or across categories  
- Export filtered subsets for further analysis  

## 📦 Installation & Running Locally  

To run the app locally, clone the repository and install dependencies:

```bash
git clone https://github.com/your-username/nyc-311-explorer.git
cd nyc-311-explorer
pip install -r requirements.txt
streamlit run streamlit_app.py
